"""Seed the MSDP online state from the production bundle.

Run immediately after every batch retrain: a retrain replaces the experts, so
Hedge evidence collected against the previous ensemble no longer means anything.
`update_latest.py` refuses to run against a state seeded from a different run.
"""
from pathlib import Path
import argparse, json, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from msdp.online.runner import initialize_online_state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument(
        "--model",
        required=True,
        help="production_model.pt hoặc production_ensemble_manifest.json",
    )
    parser.add_argument("--eta", type=float, default=0.5, help="Hedge learning rate")
    args = parser.parse_args()

    result = initialize_online_state(args.data, args.model, root=ROOT, eta=args.eta)
    _emit(result)


def _emit(payload: dict) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        print(text)
        return
    sys.stdout.flush()
    buffer.write((text + "\n").encode("utf-8"))
    buffer.flush()


if __name__ == "__main__":
    main()
