from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from msdp.pipeline import run
p=argparse.ArgumentParser(); p.add_argument("--config",default="configs/default.yaml"); p.add_argument("--data",required=True); a=p.parse_args(); result=run(a.config,a.data,ROOT); print(json.dumps({"best_params":result["best_params"],"run_label":result["run_label"]},indent=2))

