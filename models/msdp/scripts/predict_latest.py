from pathlib import Path
import argparse,json,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from msdp.inference import predict_latest_ensemble
p=argparse.ArgumentParser(); p.add_argument("--config"); p.add_argument("--data",required=True); p.add_argument("--model",required=True,help="production_model.pt hoặc production_ensemble_manifest.json"); a=p.parse_args(); payload,_=predict_latest_ensemble(a.data,a.model); target=ROOT/"artifacts/predictions"; target.mkdir(parents=True,exist_ok=True); text=json.dumps(payload,indent=2,ensure_ascii=False); (target/"latest_forecast.json").write_text(text,encoding="utf-8"); pd.json_normalize(payload["horizons"]).to_csv(target/"latest_forecast.csv",index=False); md="# Hồ sơ dự báo mới nhất theo kỳ hạn\n\n```json\n"+text+"\n```\n"; (target/"latest_forecast.md").write_text(md,encoding="utf-8"); (target/"latest_forecast_VI.md").write_text(md,encoding="utf-8"); print(text)
