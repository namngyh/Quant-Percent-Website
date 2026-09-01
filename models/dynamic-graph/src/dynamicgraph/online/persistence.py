"""On-disk representation of the online state.

Every stored state is pinned to the batch run that produced it and to the exact
return buffer it was computed from, so a stale or hand-edited artifact is
refused rather than silently continued from.
"""

from __future__ import annotations

import json
from pathlib import Path

from dynamicgraph.online.handoff import STATE_DIRECTORY
from dynamicgraph.online.state import SCHEMA_VERSION, OnlineState, OnlineStateError


def online_state_paths(root: str | Path) -> dict[str, Path]:
    directory = Path(root) / STATE_DIRECTORY
    return {
        "directory": directory,
        "state": directory / "online_state.joblib",
        "manifest": directory / "online_state_manifest.json",
        "sessions": directory / "online_sessions.csv",
    }


def save_online_state(root: str | Path, state: OnlineState) -> dict[str, Path]:
    import joblib

    paths = online_state_paths(root)
    paths["directory"].mkdir(parents=True, exist_ok=True)
    joblib.dump(state, paths["state"], compress=3)
    paths["manifest"].write_text(
        json.dumps(state.manifest(), indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return paths


def load_online_state(root: str | Path) -> OnlineState:
    import joblib

    paths = online_state_paths(root)
    if not paths["state"].exists():
        raise OnlineStateError(
            f"Chưa có online state tại {paths['state']}; chạy `init-online-state` sau `run-all`."
        )
    state: OnlineState = joblib.load(paths["state"])
    if state.schema_version != SCHEMA_VERSION:
        raise OnlineStateError(
            f"Online state dùng schema {state.schema_version}, code hiện tại là {SCHEMA_VERSION}; "
            "chạy lại `run-all` + `init-online-state`."
        )
    if paths["manifest"].exists():
        manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
        if manifest.get("buffer_sha256") != state.buffer_checksum():
            raise OnlineStateError(
                "Buffer checksum của online state không khớp manifest; state có thể đã bị sửa tay. "
                "Không tự động ghi đè — kiểm tra thủ công hoặc chạy lại `init-online-state`."
            )
    return state
