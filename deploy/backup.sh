#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: backup.sh <production-env-file> <cross-failure-domain-directory>" >&2
  exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "backup must run as root to validate Secrets and hand off staging ownership" >&2
  exit 2
fi

env_file=$1
destination=$2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python "$script_dir/preflight.py" --env-file "$env_file"
command -v age >/dev/null
command -v docker >/dev/null

env_value() {
  python "$script_dir/preflight.py" --env-file "$env_file" --get "$1"
}
NORA_POSTGRES_DATA_DIR=$(env_value NORA_POSTGRES_DATA_DIR)
NORA_MINIO_DATA_DIR=$(env_value NORA_MINIO_DATA_DIR)
NORA_BACKUP_STAGE_DIR=$(env_value NORA_BACKUP_STAGE_DIR)
NORA_POSTGRES_ADMIN_USER=$(env_value NORA_POSTGRES_ADMIN_USER)
NORA_POSTGRES_DB=$(env_value NORA_POSTGRES_DB)

: "${NORA_BACKUP_AGE_RECIPIENT:?set NORA_BACKUP_AGE_RECIPIENT in the operator environment}"
mkdir -p -m 0700 "$destination"
destination=$(CDPATH= cd -- "$destination" && pwd)
case "$destination/" in
  "$NORA_POSTGRES_DATA_DIR"/*|"$NORA_MINIO_DATA_DIR"/*|"$NORA_BACKUP_STAGE_DIR"/*)
    echo "backup destination must be outside primary data and staging paths" >&2
    exit 2
    ;;
esac

stage=$(mktemp -d "$NORA_BACKUP_STAGE_DIR/recovery-point.XXXXXX")
chmod 0700 "$stage"
chown 10001:10001 "$stage"
export NORA_BACKUP_STAGE_DIR=$stage
compose() {
  docker compose --env-file "$env_file" -f "$script_dir/compose.production.yml" "$@"
}
barrier=0

cleanup() {
  if [ "$barrier" -eq 1 ]; then
    compose --profile public start api web ingress >/dev/null 2>&1 || true
  fi
  find "$stage" -type f -exec chmod 0600 {} \; -delete 2>/dev/null || true
  find "$stage" -depth -type d -empty -delete 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
started_epoch=$(date +%s)
compose --profile public stop ingress web api
barrier=1

compose --profile ops run --rm --no-deps backup-metadata
compose exec -T db pg_dump -U "$NORA_POSTGRES_ADMIN_USER" -d "$NORA_POSTGRES_DB" -Fc >"$stage/postgres.dump"
compose --profile ops run --rm --no-deps backup-storage-client -c '
  set -eu
  mc alias set source http://storage:9000 "$(cat /run/secrets/artifact_backup_access_key)" "$(cat /run/secrets/artifact_backup_secret_key)" >/dev/null
  mkdir -p /backup/objects
  mc mirror --overwrite "source/$NORA_ARTIFACT_BUCKET" /backup/objects
'

barrier_seconds=$(($(date +%s) - started_epoch))
compose --profile public start api web ingress
barrier=0

printf '{"barrier_seconds":%s,"created_at":"%s","format_version":1}\n' \
  "$barrier_seconds" "$started_at" >"$stage/backup-record.json"
chmod 0600 "$stage/backup-record.json"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final_path="$destination/nora-$timestamp.tar.age"
temporary_path="$destination/.nora-$timestamp.tar.age.partial"
if [ -e "$final_path" ] || [ -e "$temporary_path" ]; then
  echo "append-only recovery point already exists" >&2
  exit 2
fi
tar -C "$stage" -cf - . | age --recipient "$NORA_BACKUP_AGE_RECIPIENT" --output "$temporary_path"
chmod 0600 "$temporary_path"
mv "$temporary_path" "$final_path"
echo "backup=created barrier_seconds=$barrier_seconds"
