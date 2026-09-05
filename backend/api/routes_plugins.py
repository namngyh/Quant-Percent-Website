"""Importing a Python file from the browser into the plugin folders.

The file is validated before it is written, not after: a file that fails to
parse, declares neither ``INDICATOR`` nor ``STRATEGY``, or fails to load is
rejected with the reason, and nothing lands on disk. Otherwise the folder fills
with broken files that each need cleaning out by hand.

The content arrives as text in JSON rather than as a multipart upload, which
keeps the dependency list one shorter for a feature that only ever moves a few
kilobytes of source.

These files are executed as Python once imported — the same trust level as any
script you would run yourself, which is what dropping one into ``plugins/``
already meant.
"""

from __future__ import annotations

import ast
import logging
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import settings
from backend.indicators.loader import PluginLoadError, load_plugin_file
from backend.strategy.registry import StrategyLoadError, load_strategy_file, strategy_dir

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/plugins", tags=["plugins"])

# "strategy" does not pluralise by adding an s, and the folder is
# plugins/strategies — spelling it out avoids a path that looks right.
FOLDER = {"indicator": "indicators", "strategy": "strategies"}

MAX_SOURCE_BYTES = 512_000
SAFE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-.]*\.py$")


class ImportRequest(BaseModel):
    filename: str
    content: str = Field(..., max_length=MAX_SOURCE_BYTES)
    overwrite: bool = False


def _safe_stem(filename: str) -> str:
    """Reject anything that is not a plain .py file name.

    A path is refused rather than reduced to its last component: silently
    turning `../../evil.py` into `evil.py` lands the file somewhere the caller
    did not ask for, and saying so is clearer than quietly renaming it.
    """
    if any(sep in filename for sep in ("/", "\\")) or ".." in filename:
        raise HTTPException(
            422, "Chỉ nhận tên file, không nhận đường dẫn (bỏ phần thư mục đi)."
        )

    name = Path(filename).name
    if not SAFE_NAME.match(name):
        raise HTTPException(
            422, "Tên file phải dạng `ten_file.py` (chữ, số, gạch dưới)."
        )
    if name.startswith("_"):
        raise HTTPException(422, "Tên file bắt đầu bằng `_` sẽ bị bỏ qua khi nạp.")
    return name


def _classify(source: str) -> str:
    """Decide from the source whether this is an indicator or a strategy."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise HTTPException(
            422, f"Lỗi cú pháp Python dòng {exc.lineno}: {exc.msg}"
        ) from exc

    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.FunctionDef):
            names.add(node.name)

    has_indicator = "INDICATOR" in names and "calculate" in names
    has_strategy = "STRATEGY" in names and "signals" in names

    if has_indicator and has_strategy:
        raise HTTPException(
            422, "File khai báo cả INDICATOR và STRATEGY, hãy tách thành hai file."
        )
    if has_indicator:
        return "indicator"
    if has_strategy:
        return "strategy"

    raise HTTPException(
        422,
        "Không nhận ra file. Chỉ báo cần `INDICATOR` + `calculate(df, params)`; "
        "chiến lược cần `STRATEGY` + `signals(df, params)`.",
    )


@router.post("/import")
def import_plugin(request: ImportRequest) -> dict:
    """Validate a .py file and place it in the right plugin folder."""
    name = _safe_stem(request.filename)
    kind = _classify(request.content)

    target_dir = (
        settings.plugin_indicator_dir if kind == "indicator" else strategy_dir()
    )
    destination = target_dir / name

    if destination.exists() and not request.overwrite:
        raise HTTPException(
            409,
            f"`{name}` đã tồn tại trong `plugins/{FOLDER[kind]}/`. "
            "Đổi tên file hoặc chọn ghi đè.",
        )

    # Load it from a scratch copy first, so a file that blows up on import
    # never reaches the folder the platform scans.
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / name
        probe.write_text(request.content, encoding="utf-8")

        try:
            if kind == "indicator":
                spec = load_plugin_file(probe)
                summary = {
                    "name": spec.name,
                    "kind": spec.kind,
                    "params": [p.name for p in spec.params],
                    "outputs": [o.key for o in spec.outputs],
                }
            else:
                spec = load_strategy_file(probe)
                summary = {
                    "name": spec.name,
                    "side": spec.side,
                    "params": [p.name for p in spec.params],
                }
        except (PluginLoadError, StrategyLoadError) as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            log.exception("import validation failed for %s", name)
            raise HTTPException(422, f"{type(exc).__name__}: {exc}") from exc

        shutil.copyfile(probe, destination)

    log.info("imported %s %s as %s", kind, name, spec.id)
    return {
        "imported": True,
        "kind": kind,
        "filename": name,
        "path": f"plugins/{FOLDER[kind]}/{name}",
        "spec": summary,
    }
