from __future__ import annotations
import hashlib, json, os, platform, random, subprocess, sys
from pathlib import Path
import numpy as np
import torch

def set_global_seed(seed: int, deterministic: bool = True) -> None:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False if deterministic else torch.backends.cudnn.benchmark
    torch.backends.cudnn.deterministic = deterministic
    torch.use_deterministic_algorithms(deterministic, warn_only=True)

def file_hash(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def metadata(config: dict, data_path: str | Path, dates=None) -> dict:
    try: commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception: commit = None
    return {"python": sys.version, "os": platform.platform(), "processor": platform.processor(),
            "torch": torch.__version__, "cuda": torch.cuda.is_available(), "seed": config.get("seed"),
            "git_commit": commit, "data_sha256": file_hash(data_path), "date_range": dates, "config": config}

def save_metadata(payload: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

