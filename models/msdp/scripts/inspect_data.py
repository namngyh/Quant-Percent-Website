from pathlib import Path
import argparse, json, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from msdp.data_io import load_market_data
from msdp.data_quality import assess_quality
p=argparse.ArgumentParser(); p.add_argument("--data",required=True); a=p.parse_args(); print(json.dumps(assess_quality(load_market_data(a.data)),indent=2))

