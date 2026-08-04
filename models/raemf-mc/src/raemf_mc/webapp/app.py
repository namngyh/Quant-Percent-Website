"""FastAPI application for the local RAEMF-MC dashboard.

Chạy: `uvicorn raemf_mc.webapp.app:app` từ thư mục gốc repo (hoặc dùng
`start_ui.bat`). Ứng dụng chỉ phục vụ local, đọc trực tiếp các file trong
`outputs/` và điều khiển các job qua CLI của package.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from raemf_mc.data.loader import load_price_data
from raemf_mc.webapp.jobs import JOB_DEFINITIONS, JobBusyError, JobManager

ROOT = Path(os.environ.get("RAEMF_ROOT", Path.cwd())).resolve()
DATA_FILE = ROOT / "VNINDEX_Daily.csv"
MONITOR_DIR = ROOT / "outputs" / "current_monitor"
INCOMING_DIR = ROOT / "incoming"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="RAEMF-MC Dashboard", docs_url=None, redoc_url=None)
jobs = JobManager(ROOT)

_price_cache: dict[str, object] = {}


def _load_prices() -> pd.DataFrame:
    """Load the canonical price history, cached by file mtime/size."""
    if not DATA_FILE.exists():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy {DATA_FILE.name} trong {ROOT}")
    stat = DATA_FILE.stat()
    key = f"{stat.st_mtime_ns}:{stat.st_size}"
    if _price_cache.get("key") != key:
        df, _meta = load_price_data(DATA_FILE)
        _price_cache["key"] = key
        _price_cache["df"] = df
    return _price_cache["df"]  # type: ignore[return-value]


def _json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def status() -> JSONResponse:
    payload: dict[str, object] = {"root": str(ROOT)}
    try:
        df = _load_prices()
        closes = df["close"].tolist()
        payload["data"] = {
            "rows": len(df),
            "end_date": df["date"].iloc[-1].strftime("%Y-%m-%d"),
            "last_close": closes[-1],
            "prev_close": closes[-2] if len(closes) > 1 else None,
        }
    except HTTPException:
        payload["data"] = None
    pending = []
    if INCOMING_DIR.is_dir():
        pending = sorted(
            p.name for p in INCOMING_DIR.iterdir() if p.is_file() and p.suffix.lower() in {".csv", ".txt"}
        )
    payload["incoming_files"] = pending
    outlook_path = MONITOR_DIR / "current_outlook.json"
    payload["outlook_as_of"] = None
    if outlook_path.exists():
        try:
            payload["outlook_as_of"] = json.loads(outlook_path.read_text(encoding="utf-8")).get("as_of_date")
        except (OSError, json.JSONDecodeError):
            pass
    current = jobs.current
    payload["job"] = current.to_dict() if current else None
    return JSONResponse(payload)


@app.get("/api/price")
def price(days: int = 365) -> JSONResponse:
    df = _load_prices()
    if days > 0:
        df = df.tail(days)
    max_points = 1600
    if len(df) > max_points:
        stride = math.ceil(len(df) / max_points)
        sampled = df.iloc[::stride]
        if sampled.index[-1] != df.index[-1]:
            sampled = pd.concat([sampled, df.tail(1)])
        df = sampled
    return JSONResponse(
        {
            "dates": [d.strftime("%Y-%m-%d") for d in df["date"]],
            "close": [_json_safe(round(float(v), 2)) for v in df["close"]],
        }
    )


@app.get("/api/outlook")
def outlook() -> JSONResponse:
    path = MONITOR_DIR / "current_outlook.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Chưa có current_outlook.json — hãy chạy báo cáo trước.")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@app.get("/api/mc-quantiles")
def mc_quantiles(horizon: int = 20) -> JSONResponse:
    path = MONITOR_DIR / f"current_monte_carlo_quantiles_{horizon}.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Không có file quantiles cho horizon {horizon}.")
    df = pd.read_csv(path)
    columns = {col: [_json_safe(float(v)) for v in df[col]] for col in df.columns if col != "step"}
    summary_path = MONITOR_DIR / "current_monte_carlo_summary.csv"
    summary: dict[str, object] = {}
    if summary_path.exists():
        sdf = pd.read_csv(summary_path)
        row = sdf.loc[sdf["horizon"] == horizon]
        if len(row):
            record = row.iloc[0].to_dict()
            summary = {k: _json_safe(v if not isinstance(v, float) else float(v)) for k, v in record.items()}
    return JSONResponse({"steps": [int(v) for v in df["step"]], "quantiles": columns, "summary": summary})


@app.get("/api/report")
def report() -> JSONResponse:
    path = MONITOR_DIR / "report_for_nonspecialists.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Chưa có báo cáo — hãy chạy báo cáo trước.")
    return JSONResponse({"markdown": path.read_text(encoding="utf-8")})


@app.get("/api/figures")
def figures() -> JSONResponse:
    groups = []
    for name, directory in [
        ("Theo dõi hiện tại", MONITOR_DIR / "figures"),
        ("Nghiên cứu (outputs/latest)", ROOT / "outputs" / "latest" / "figures"),
    ]:
        if not directory.is_dir():
            continue
        rel = directory.relative_to(ROOT / "outputs").as_posix()
        files = []
        newest = 0.0
        for path in sorted(directory.glob("*.png")):
            mtime = path.stat().st_mtime
            newest = max(newest, mtime)
            # mtime làm cache-buster: ảnh vẽ lại là trình duyệt tải bản mới ngay.
            files.append(f"/files/{rel}/{path.name}?v={int(mtime)}")
        groups.append(
            {
                "group": name,
                "files": files,
                "updated": datetime.fromtimestamp(newest).strftime("%H:%M %d/%m/%Y") if files else None,
            }
        )
    return JSONResponse({"groups": groups})


@app.get("/api/jobs")
def job_state() -> JSONResponse:
    current = jobs.current
    return JSONResponse(
        {
            "current": current.to_dict() if current else None,
            "log": jobs.log_tail(),
            "history": [job.to_dict() for job in jobs.history],
        }
    )


@app.post("/api/jobs/cancel")
def job_cancel() -> JSONResponse:
    return JSONResponse({"cancelled": jobs.cancel()})


@app.post("/api/jobs/{kind}")
def job_start(kind: str) -> JSONResponse:
    if kind not in JOB_DEFINITIONS:
        raise HTTPException(status_code=404, detail=f"Không có loại tác vụ '{kind}'.")
    try:
        job = jobs.start(kind)
    except JobBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(job.to_dict())


app.mount("/files", StaticFiles(directory=ROOT / "outputs"), name="files")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
