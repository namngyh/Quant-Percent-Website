from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from msdp.reporting import generate_report
p=argparse.ArgumentParser(); p.add_argument("--run",default="latest"); a=p.parse_args(); generate_report(json.loads((ROOT/"reports/tables/final_metrics.json").read_text()),json.loads((ROOT/"reports/tables/data_quality.json").read_text()),json.loads((ROOT/"artifacts/predictions/latest_forecast.json").read_text()),ROOT/"reports"); print("Reports regenerated from artifacts for run",a.run)

