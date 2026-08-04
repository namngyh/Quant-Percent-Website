set -eu

stamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
target="/backups/market_${stamp}.dump"

pg_dump --format=custom --file="$target"
find /backups -type f -name 'market_*.dump' \
  -mtime "+${BACKUP_RETENTION_DAYS:-14}" -delete

echo "Backup created: $target"
