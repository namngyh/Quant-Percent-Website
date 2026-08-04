"""Background job runner for the local web UI.

Chạy các chu trình (daily, retrain) dưới dạng subprocess gọi CLI của chính
package, ghi log ra file trong `outputs/webapp_jobs/`. Mỗi thời điểm chỉ cho
phép một job chạy để tránh hai tiến trình cùng ghi vào `outputs/`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class JobBusyError(RuntimeError):
    """Raised when a job is requested while another one is still running."""


JOB_DEFINITIONS: dict[str, dict[str, object]] = {
    "daily": {
        "label": "Cập nhật dữ liệu và chạy báo cáo hôm nay",
        "commands": [["{python}", "-m", "raemf_mc.cli", "daily"]],
    },
    "retrain": {
        "label": "Retrain toàn bộ pipeline rồi cập nhật báo cáo",
        "commands": [
            ["{python}", "-m", "raemf_mc.cli", "run", "--data", "VNINDEX_Daily.csv", "--config", "configs/laptop.yaml"],
            ["{python}", "-m", "raemf_mc.cli", "current-report"],
        ],
    },
}


@dataclass
class Job:
    id: str
    kind: str
    label: str
    state: str = "running"  # running | success | failed | cancelled
    returncode: int | None = None
    started_at: str = ""
    finished_at: str | None = None
    log_file: str = ""
    current_step: int = 0
    total_steps: int = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "state": self.state,
            "returncode": self.returncode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
        }


class JobManager:
    def __init__(self, root: Path, log_dir: Path | None = None) -> None:
        self.root = Path(root)
        self.log_dir = Path(log_dir) if log_dir else self.root / "outputs" / "webapp_jobs"
        self._lock = threading.Lock()
        self._current: Job | None = None
        self._process: subprocess.Popen | None = None
        self._cancel_requested = False
        self.history: list[Job] = []

    @property
    def current(self) -> Job | None:
        return self._current

    def start(self, kind: str) -> Job:
        if kind not in JOB_DEFINITIONS:
            raise ValueError(f"Unknown job kind: {kind}")
        with self._lock:
            if self._current is not None and self._current.state == "running":
                raise JobBusyError("Đang có tác vụ khác chạy, hãy chờ xong hoặc hủy trước.")
            definition = JOB_DEFINITIONS[kind]
            commands = [[part.format(python=sys.executable) for part in cmd] for cmd in definition["commands"]]
            self.log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            job = Job(
                id=uuid.uuid4().hex[:12],
                kind=kind,
                label=str(definition["label"]),
                started_at=datetime.now().isoformat(timespec="seconds"),
                log_file=str(self.log_dir / f"{stamp}_{kind}.log"),
                total_steps=len(commands),
            )
            self._current = job
            self._cancel_requested = False
            thread = threading.Thread(target=self._run, args=(job, commands), daemon=True)
            thread.start()
            return job

    def cancel(self) -> bool:
        with self._lock:
            if self._current is None or self._current.state != "running":
                return False
            self._cancel_requested = True
            if self._process is not None and self._process.poll() is None:
                self._process.terminate()
            return True

    def log_tail(self, max_bytes: int = 20_000) -> str:
        job = self._current
        if job is None or not job.log_file:
            return ""
        path = Path(job.log_file)
        if not path.exists():
            return ""
        data = path.read_bytes()
        if len(data) > max_bytes:
            data = data[-max_bytes:]
        return data.decode("utf-8", errors="replace")

    def _run(self, job: Job, commands: list[list[str]]) -> None:
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("MPLBACKEND", "Agg")
        env["PYTHONPATH"] = str(self.root / "src") + os.pathsep + env.get("PYTHONPATH", "")
        returncode = 0
        try:
            with Path(job.log_file).open("a", encoding="utf-8") as log:
                for index, command in enumerate(commands, start=1):
                    job.current_step = index
                    log.write(f"$ {' '.join(command)}\n")
                    log.flush()
                    process = subprocess.Popen(
                        command,
                        cwd=self.root,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env=env,
                    )
                    with self._lock:
                        self._process = process
                    returncode = process.wait()
                    if self._cancel_requested:
                        log.write("\n[Đã hủy theo yêu cầu người dùng]\n")
                        break
                    if returncode != 0:
                        log.write(f"\n[Lệnh kết thúc với mã lỗi {returncode}]\n")
                        break
        except Exception as exc:  # noqa: BLE001 - surfaced through job state
            returncode = -1
            try:
                with Path(job.log_file).open("a", encoding="utf-8") as log:
                    log.write(f"\n[Lỗi runner: {exc}]\n")
            except OSError:
                pass
        with self._lock:
            self._process = None
            job.returncode = returncode
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            if self._cancel_requested:
                job.state = "cancelled"
            elif returncode == 0:
                job.state = "success"
            else:
                job.state = "failed"
            self.history.insert(0, job)
            del self.history[20:]
