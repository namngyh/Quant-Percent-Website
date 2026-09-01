"""Run MSDP inference against the current data and write the forecast JSON.

NO LONGER PART OF THE DAILY JOB, and deliberately not a drop-in substitute for
what replaced it. `daily-update.bat` now calls MSDP's own online tier
(`scripts/sync_source.py` then `scripts/update_latest.py`), which scores the
forecasts whose horizon has elapsed, folds that evidence into the Hedge gate
posterior, and only then re-runs inference. This script skips all of that and
runs the ensemble cold, so it publishes DIFFERENT numbers under the same
`model_id`.

Use it to reproduce a forecast without touching the online state - never as a
silent fallback when `update_latest.py` fails. If the online step is broken,
the honest outcome is the run being marked failed, not a different model's
answer published in its place.

MSDP loads an already-trained production ensemble and predicts in well under a
second, so this can run daily right after the market close — no retraining.

It needs MSDP's own environment (Python >=3.10,<3.13 plus torch), which is why
this is a separate step from `load_model_outputs.py`: the loader only needs a
PostgreSQL driver and runs anywhere.

    C:\\qpvenv\\msdp\\Scripts\\python.exe database/scripts/run_msdp_inference.py \\
        --model-root models/msdp --out artifacts/msdp_latest.json

Refresh the input first so the forecast is not computed on a stale snapshot:

    python database/scripts/export_vnindex_daily.py --repo-root .
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-root", required=True, help="Path to models/msdp"
    )
    parser.add_argument("--out", required=True, help="Where to write the JSON")
    parser.add_argument(
        "--data",
        help="Override the CSV; defaults to <model-root>/data/raw/VNINDEX_Daily.csv",
    )
    parser.add_argument(
        "--manifest",
        help="Override the production manifest under artifacts/models/",
    )
    args = parser.parse_args()

    root = Path(args.model_root).resolve()
    sys.path.insert(0, str(root / "src"))
    try:
        from msdp.inference import predict_latest_ensemble
    except ModuleNotFoundError as exc:
        sys.exit(
            f"Cannot import msdp ({exc}). Run this with MSDP's interpreter, "
            "e.g. C:\\qpvenv\\msdp\\Scripts\\python.exe"
        )

    data = Path(args.data) if args.data else root / "data" / "raw" / "VNINDEX_Daily.csv"
    manifest = (
        Path(args.manifest)
        if args.manifest
        else root / "artifacts" / "models" / "production_ensemble_manifest.json"
    )
    for path, label in ((data, "data"), (manifest, "manifest")):
        if not path.exists():
            sys.exit(f"Missing {label}: {path}")

    started = time.time()
    latest, _seed_predictions = predict_latest_ensemble(data, manifest)
    elapsed = time.time() - started

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(latest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"inference took {elapsed:.1f}s")
    print(f"run_id      : {latest.get('run_id')}")
    print(f"data_date   : {latest.get('data_date')}")
    print(f"spot        : {latest.get('current_vnindex')}")
    print(f"horizons    : {[h['horizon'] for h in latest.get('horizons', [])]}")
    print(f"wrote       : {out}")
    if "quick" in str(latest.get("run_id", "")):
        print(
            "\nWARNING: this production artifact came from a `quick` run "
            "(few trials/folds/seeds). Re-run MSDP with the full config "
            "before publishing these numbers.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
