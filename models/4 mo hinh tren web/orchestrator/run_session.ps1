<#
.SYNOPSIS
    Cap nhat ca 4 mo hinh sau khi dong phien, doc tu TimescaleDB.

.DESCRIPTION
    Bon mo hinh doc lap voi nhau (khac stack, khac artifact, khong dung chung
    dong code nao), nen mot mo hinh hong KHONG duoc chan ba cai con lai. Moi
    buoc chay trong try/catch rieng va ket qua tong hop duoc in ra cuoi cung.

    Thu tu trong tung repo la bat buoc:
        sync-source      -> chup snapshot tu DB (tang batch van hash mot file)
        update-latest    -> ap phien moi, khong refit gi

    Script nay KHONG dung toi D:\Quant-Percent-Website\daily-update.bat, la
    pipeline dang chay that cua website (Task Scheduler 15:15 T2-T6). Hai duong
    doc cung mot database va khong ghi de len nhau: cai kia ghi vao schema
    `quant.*`, cai nay ghi vao artifacts cua tung repo.

.PARAMETER Root
    Thu muc chua 4 repo. Mac dinh la thu muc cha cua script nay.

.PARAMETER SkipMarketCheck
    Bo qua kiem tra "hom nay co bar ngay chua". Dung khi chay lai bang tay.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File orchestrator\run_session.ps1
#>
[CmdletBinding()]
param(
    [string] $Root = (Split-Path -Parent $PSScriptRoot),
    [switch] $SkipMarketCheck
)

$ErrorActionPreference = 'Continue'

$LogDirectory = Join-Path $PSScriptRoot 'logs'
if (-not (Test-Path $LogDirectory)) { New-Item -ItemType Directory -Path $LogDirectory | Out-Null }
$Today = Get-Date -Format 'yyyy-MM-dd'
$LogFile = Join-Path $LogDirectory "session-$Today.log"

function Write-Log {
    param([string] $Message)
    $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $Message
    Write-Output $line
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

$Repos = @{
    RAFF         = Join-Path $Root 'RARF-FHE-Regime-Aware-Random-Forest-Forecasting-Hybrid-Engine'
    DynamicGraph = Join-Path $Root 'Dynamic-Graph'
    MSDP         = Join-Path $Root 'MSDP'
    Tempus       = Join-Path $Root 'Tempus-VIN'
}

# Tempus co venv rieng (torch CUDA); ba cai con lai chay bang Python he thong.
$TempusPython = Join-Path $Repos.Tempus '.venv\Scripts\python.exe'
$SystemPython = 'python'

$Results = [ordered]@{}

function Invoke-Step {
    <#  Chay mot lenh, ghi log, tra ve $true/$false. Khong bao gio nem loi ra
        ngoai: mot mo hinh hong khong duoc chan cac mo hinh con lai. #>
    param(
        [string] $Name,
        [string] $WorkingDirectory,
        [string] $Executable,
        [string[]] $Arguments
    )
    Write-Log "  -> $Name"
    try {
        Push-Location $WorkingDirectory
        $output = & $Executable @Arguments 2>&1
        $code = $LASTEXITCODE
        Pop-Location
        $output | ForEach-Object { Add-Content -Path $LogFile -Value "     $_" -Encoding utf8 }
        if ($code -ne 0) {
            Write-Log "     [LOI] exit code $code"
            return $false
        }
        # Dong JSON cuoi cung la ket qua; in gon lai cho nguoi doc log.
        $summary = ($output | Select-String -Pattern '"status"' | Select-Object -Last 1)
        if ($summary) { Write-Log "     $($summary.Line.Trim())" }
        return $true
    }
    catch {
        if ((Get-Location).Path -ne $Root) { Pop-Location -ErrorAction SilentlyContinue }
        Write-Log "     [LOI] $_"
        return $false
    }
}

Write-Log '=============================================='
Write-Log "Bat dau cap nhat 4 mo hinh: $Today"

# --- Hom nay co phien khong? -------------------------------------------------
# Chay model tren du lieu cu roi ghi de du bao dang dung con te hon la khong chay.
if (-not $SkipMarketCheck) {
    $dayOfWeek = [int](Get-Date).DayOfWeek
    if ($dayOfWeek -eq 0 -or $dayOfWeek -eq 6) {
        Write-Log 'Cuoi tuan - bo qua.'
        exit 0
    }
    $probe = @'
import sys, os
sys.path.insert(0, "src")
from vnindex_model.dotenv import load_env_file
from vnindex_model.data_source import build_market_data_source
import datetime as dt
load_env_file()
source = build_market_data_source({
    "backend": "postgres", "dsn_env": "VNINDEX_MARKET_DSN", "table": "bars_1d",
    "symbol": "VNINDEX", "column_map": {"date": "trading_date", "close": "close"},
})
try:
    print(source.latest_date().date())
finally:
    source.close()
'@
    Push-Location $Repos.RAFF
    $latest = & $SystemPython -c $probe 2>&1 | Select-Object -Last 1
    Pop-Location
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Khong doc duoc database: $latest"
        exit 1
    }
    Write-Log "Phien moi nhat trong bars_1d: $latest"
    if ("$latest".Trim() -ne $Today) {
        Write-Log "Chua co bar ngay cho $Today (co the la ngay nghi, hoac backfill chua chay). Bo qua."
        Write-Log 'Chay lai bang tay voi -SkipMarketCheck neu chac chan muon tiep tuc.'
        exit 0
    }
}

# --- 1. RAFF (VN-Index) ------------------------------------------------------
Write-Log '[1/4] RAFF'
$ok = Invoke-Step 'sync-source' $Repos.RAFF $SystemPython @(
    '-m', 'vnindex_model.cli', 'sync-source', '--config', 'configs/default.yaml')
if ($ok) {
    $ok = Invoke-Step 'update-latest' $Repos.RAFF $SystemPython @(
        '-m', 'vnindex_model.cli', 'update-latest', '--config', 'configs/default.yaml')
}
$Results['RAFF'] = $ok

# --- 2. Dynamic Graph (VN30) -------------------------------------------------
# Khong co buoc sync: connector Postgres doc thang, khong qua file trung gian.
Write-Log '[2/4] Dynamic Graph'
$Results['DynamicGraph'] = Invoke-Step 'update-latest' $Repos.DynamicGraph $SystemPython @(
    '-m', 'dynamicgraph.cli', 'update-latest', '--config', 'config/local.yaml')

# --- 3. MSDP (VN-Index) ------------------------------------------------------
Write-Log '[3/4] MSDP'
$msdpModel = 'artifacts/models/production_ensemble_manifest.json'
$msdpData = 'data/raw/VNINDEX_Daily_db.csv'
$ok = Invoke-Step 'sync_source' $Repos.MSDP $SystemPython @(
    'scripts/sync_source.py', '--config', 'configs/default.yaml')
if ($ok) {
    $ok = Invoke-Step 'update_latest' $Repos.MSDP $SystemPython @(
        'scripts/update_latest.py', '--data', $msdpData, '--model', $msdpModel)
}
$Results['MSDP'] = $ok

# --- 4. Tempus-VIN / RAEMF-VB-MC --------------------------------------------
# `predict` nap lai bundle da fit; khong fit gi o day (fit ton hang gio).
Write-Log '[4/4] Tempus-VIN'
if (Test-Path $TempusPython) {
    $Results['Tempus'] = Invoke-Step 'predict' $Repos.Tempus $TempusPython @(
        '-m', 'raemf_mc.cli', 'predict', '--source', 'database')
}
else {
    Write-Log "  [BO QUA] Khong thay venv: $TempusPython"
    $Results['Tempus'] = $false
}

# --- Tong ket ----------------------------------------------------------------
Write-Log '----------------------------------------------'
$failed = @()
foreach ($name in $Results.Keys) {
    $status = if ($Results[$name]) { 'OK' } else { 'LOI' }
    Write-Log ("  {0,-14} {1}" -f $name, $status)
    if (-not $Results[$name]) { $failed += $name }
}
Write-Log "Ket thuc. Log: $LogFile"

# Exit code khac 0 de Task Scheduler ghi nhan, nhung chi khi CO loi that.
if ($failed.Count -gt 0) { exit 1 }
exit 0
