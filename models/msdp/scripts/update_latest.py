"""Apply every newly observable session without retraining anything.

Scores the forecasts whose horizon has elapsed, folds that evidence into the
Hedge gate posterior, re-runs inference with the posterior fused in, and
republishes `artifacts/predictions/latest_forecast.*` with the same schema
`predict_latest.py` writes.
"""
from pathlib import Path
import argparse, json, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from msdp.online.runner import update_latest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument(
        "--model",
        required=True,
        help="production_model.pt hoặc production_ensemble_manifest.json",
    )
    args = parser.parse_args()

    result = update_latest(args.data, args.model, root=ROOT)
    text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        print(text)
    else:
        sys.stdout.flush()
        buffer.write((text + "\n").encode("utf-8"))
        buffer.flush()


if __name__ == "__main__":
    main()
