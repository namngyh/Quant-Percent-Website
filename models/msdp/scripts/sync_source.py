"""Refresh the batch input snapshot from the configured data source.

Run this before `train.py` / `evaluate.py` / `predict_latest.py` so every stage
reads the same dated file. Scheduled use: once per trading day after the close,
ahead of `update_latest.py`.
"""
from pathlib import Path
import argparse, json, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from msdp.data_sync import sync_source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs/default.yaml"))
    parser.add_argument("--destination", default=None, help="Override data.path")
    args = parser.parse_args()

    result = sync_source(args.config, destination=args.destination, root=ROOT)
    text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    # Task Scheduler redirects stdout to a file, which defaults to cp1252 on
    # Windows and would raise UnicodeEncodeError on the Vietnamese messages.
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        print(text)
    else:
        sys.stdout.flush()
        buffer.write((text + "\n").encode("utf-8"))
        buffer.flush()
    if result.get("history_rewritten"):
        raise SystemExit(
            f"Lịch sử bị sửa ở {result['rewritten_count']} phiên "
            f"({result['rewritten_dates'][:5]}). Chạy lại train + init_online_state "
            "thay vì update_latest."
        )


if __name__ == "__main__":
    main()
