param([string]$Config="configs/quick.yaml",[string]$Data="data/raw/VNINDEX_Daily.csv")
$ErrorActionPreference="Stop"
python scripts/run_all.py --config $Config --data $Data

