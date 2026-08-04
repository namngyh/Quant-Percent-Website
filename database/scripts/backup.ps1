# Backup database + parquet vao backup\ — chay bat ky luc nao (khong can dung he thong)
#   powershell -File "scripts\backup.ps1"
# Giu 8 ban gan nhat, ban cu hon tu xoa.

$root = Split-Path $PSScriptRoot -Parent
$backupDir = Join-Path $root "backup"
New-Item -ItemType Directory -Force $backupDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd"
$env:Path += ";C:\Program Files\Docker\Docker\resources\bin"

# 1) Dump database (logic backup — khoi phuc duoc sang bat ky may nao)
$dump = Join-Path $backupDir "market_$stamp.dump"
docker exec qp-timescaledb pg_dump -U quant -d market -Fc -f /tmp/market.dump
docker cp qp-timescaledb:/tmp/market.dump $dump
docker exec qp-timescaledb rm /tmp/market.dump
Write-Host "DB dump: $dump ($([math]::Round((Get-Item $dump).Length/1MB,1)) MB)"

# 2) Nen parquet tho — qua staging de bo qua file NGAY HOM NAY dang duoc
#    ingestion mo (file do chua hoan chinh, mai backup se co ban chot)
$zip = Join-Path $backupDir "parquet_$stamp.zip"
$staging = Join-Path $env:TEMP "qp_parquet_staging"
robocopy (Join-Path $root "data\raw") $staging /E /R:0 /W:0 /NFL /NDL /NJH /NJS | Out-Null
Compress-Archive -Path "$staging\*" -DestinationPath $zip -Force
Remove-Item $staging -Recurse -Force
Write-Host "Parquet:  $zip ($([math]::Round((Get-Item $zip).Length/1MB,1)) MB)"

# 3) Don ban cu — giu 8 ban moi nhat moi loai
foreach ($pattern in @("market_*.dump", "parquet_*.zip")) {
    Get-ChildItem $backupDir -Filter $pattern | Sort-Object Name -Descending |
        Select-Object -Skip 8 | Remove-Item -Force
}
Write-Host "Xong. Khoi phuc DB: docker exec -i qp-timescaledb pg_restore -U quant -d market --clean < file.dump"
