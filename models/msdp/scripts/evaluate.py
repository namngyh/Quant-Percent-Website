from pathlib import Path
import argparse,json
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(); p.add_argument("--config"); p.add_argument("--data"); a=p.parse_args(); path=ROOT/"reports/tables/final_metrics.json"
if not path.exists(): raise SystemExit("No evaluation artifact. Run scripts/run_all.py first.")
print(json.dumps(json.loads(path.read_text(encoding="utf-8")),indent=2))

