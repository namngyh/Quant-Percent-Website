from pathlib import Path
import argparse, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from msdp.data_io import load_market_data
from msdp.features import build_features
from msdp.targets import build_targets
p=argparse.ArgumentParser(); p.add_argument("--data",required=True); a=p.parse_args(); d=load_market_data(a.data); f,m=build_features(d); t=build_targets(d); out=Path("data/processed"); out.mkdir(parents=True,exist_ok=True); d.join(f).join(t).to_csv(out/"model_frame.csv",index=False); m.to_csv(out/"feature_metadata.csv",index=False)

