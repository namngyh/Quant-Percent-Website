"""Where the online state lives on disk, and the guards on loading it.

JSON rather than a pickle: the state is small, a human has to be able to read it
when a session looks wrong, and unlike the model artefacts it is rewritten every
trading day. The manifest sits next to it as the audit record, and the pickled
state file is gitignored while the manifest is not.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .state import OnlineState

ARTIFACTS_DIRECTORY = "artifacts"
STATE_DIRECTORY = "online_state"
STATE_NAME = "online_state.json"
MANIFEST_NAME = "online_manifest.json"
SESSIONS_NAME = "online_sessions.csv"


class OnlineStateError(RuntimeError):
    """Raised when a stored online state cannot be trusted as-is."""


def online_state_paths(root: str | Path) -> dict[str, Path]:
    """Everything the online tier writes lives under `artifacts/online_state/`,
    next to the model artefacts it is derived from."""
    directory = Path(root) / ARTIFACTS_DIRECTORY / STATE_DIRECTORY
    return {
        "directory": directory,
        "state": directory / STATE_NAME,
        "manifest": directory / MANIFEST_NAME,
        "sessions": directory / SESSIONS_NAME,
    }


def save_online_state(root: str | Path, state: OnlineState) -> dict[str, Path]:
    paths = online_state_paths(root)
    paths["directory"].mkdir(parents=True, exist_ok=True)
    _write_json(paths["state"], state.to_dict())
    _write_json(paths["manifest"], state.manifest())
    return paths


def load_online_state(root: str | Path) -> OnlineState:
    paths = online_state_paths(root)
    if not paths["state"].exists():
        raise OnlineStateError(
            f"Chưa có online state tại {paths['state']}; chạy `scripts/init_online_state.py` trước."
        )
    payload = json.loads(paths["state"].read_text(encoding="utf-8"))
    return OnlineState.from_dict(payload)


def assert_state_matches_run(state: OnlineState, run_id: str) -> None:
    """Refuse to advance a state seeded from a different batch run.

    Every retrain resets the online tier. Without this check `update_latest`
    would keep applying Hedge evidence collected against the *previous*
    ensemble's experts to the new one, and nothing would report an error.
    """
    seeded = str(state.source_run_metadata.get("run_id", ""))
    if seeded and str(run_id) and seeded != str(run_id):
        raise OnlineStateError(
            f"Online state được seed từ run {seeded!r} nhưng bundle hiện tại là {run_id!r}; "
            "chạy lại `scripts/init_online_state.py` sau mỗi lần train."
        )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write atomically: a half-written state is worse than no state at all."""
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    temporary.replace(path)
