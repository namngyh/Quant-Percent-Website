from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import platform
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from msdp.pipeline import run


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


p=argparse.ArgumentParser(); p.add_argument("--config",default="configs/default.yaml"); p.add_argument("--data",required=True); a=p.parse_args()
summary=run(a.config,a.data,ROOT); run_id=summary["run_id"]; commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(); command=[sys.executable,"-m","pytest","-q"]
result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True); header=[f"Git commit: {commit}",f"Run ID: {run_id}",f"Config: {a.config}",f"Data hash: {sha256(Path(a.data))}",f"Python: {platform.python_version()}",f"Platform: {platform.platform()}",f"Generated at: {datetime.now(timezone.utc).isoformat()}",f"Command: {' '.join(command)}",""]
test_dir=ROOT/"reports/runs"/run_id; test_dir.mkdir(parents=True,exist_ok=True); test_path=test_dir/"test_results.txt"; test_path.write_text("\n".join(header)+result.stdout+result.stderr,encoding="utf-8")
test_manifest={"run_id":run_id,"git_commit":commit,"path":str(test_path.relative_to(ROOT)).replace('\\','/'),"exit_code":result.returncode,"generated_at":datetime.now(timezone.utc).isoformat()}; (ROOT/"reports/latest_test_manifest.json").write_text(json.dumps(test_manifest,indent=2,ensure_ascii=False),encoding="utf-8")
summary.update({"test_log_path":test_manifest["path"],"test_exit_code":result.returncode}); (ROOT/"artifacts/run_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8"); (ROOT/"artifacts/runs"/run_id/"run_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2,ensure_ascii=False)); print(result.stdout)
if result.returncode: raise SystemExit(result.returncode)
