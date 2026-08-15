#!/bin/sh
set -eu

if [ "$#" -ne 4 ]; then
  echo "usage: restore.sh <isolated-env-file> <recovery-point.tar.age> <age-identity-file> <report-directory>" >&2
  exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "restore must run as root to validate Secrets and hand off staging ownership" >&2
  exit 2
fi
if [ "${NORA_ISOLATED_RESTORE_CONFIRMATION:-}" != "isolated-no-public-ingress" ]; then
  echo "set NORA_ISOLATED_RESTORE_CONFIRMATION=isolated-no-public-ingress" >&2
  exit 2
fi

env_file=$1
recovery_point=$2
identity_file=$3
report_directory=$4
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python "$script_dir/preflight.py" --env-file "$env_file"
command -v age >/dev/null

env_value() {
  python "$script_dir/preflight.py" --env-file "$env_file" --get "$1"
}
NORA_COMPOSE_PROJECT=$(env_value NORA_COMPOSE_PROJECT)
NORA_BACKUP_STAGE_DIR=$(env_value NORA_BACKUP_STAGE_DIR)
NORA_POSTGRES_ADMIN_USER=$(env_value NORA_POSTGRES_ADMIN_USER)
NORA_POSTGRES_DB=$(env_value NORA_POSTGRES_DB)

case "${NORA_COMPOSE_PROJECT:-}" in
  *restore*|*rehearsal*) ;;
  *) echo "isolated restore project name must contain restore or rehearsal" >&2; exit 2 ;;
esac

stage=$(mktemp -d "$NORA_BACKUP_STAGE_DIR/restore-input.XXXXXX")
chmod 0700 "$stage"
compose() {
  docker compose --env-file "$env_file" -f "$script_dir/compose.production.yml" "$@"
}
cleanup() {
  find "$stage" -type f -exec chmod 0600 {} \; -delete 2>/dev/null || true
  find "$stage" -depth -type d -empty -delete 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

started_epoch=$(date +%s)
age --decrypt --identity "$identity_file" "$recovery_point" >"$stage/recovery.tar"
chmod 0600 "$stage/recovery.tar"
payload="$stage/payload"
python "$script_dir/extract_recovery.py" --archive "$stage/recovery.tar" --destination "$payload"
chown -R 10001:10001 "$payload"
export NORA_BACKUP_STAGE_DIR=$payload
test -s "$payload/postgres.dump"
test -f "$payload/artifact-manifest.jsonl"
test -f "$payload/artifact-deletion-ledger.jsonl"
test -f "$payload/backup-metadata.json"
test -f "$payload/backup-record.json"

compose up -d db storage
compose --profile initialize run --rm storage-init
compose exec -T db pg_restore --clean --if-exists --no-owner --no-acl \
  -U "$NORA_POSTGRES_ADMIN_USER" -d "$NORA_POSTGRES_DB" <"$payload/postgres.dump"
compose --profile initialize run --rm db-init
compose --profile ops run --rm --no-deps restore-storage-client -c '
  set -eu
  mc alias set target http://storage:9000 "$(cat /run/secrets/minio_root_user)" "$(cat /run/secrets/minio_root_password)" >/dev/null
  mc mb --ignore-existing "target/$NORA_ARTIFACT_BUCKET"
  mc mirror --overwrite /backup/objects "target/$NORA_ARTIFACT_BUCKET"
'
compose --profile ops run --rm --no-deps reconcile
compose up -d api web
compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/live', timeout=2)"
compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)"

mkdir -p -m 0700 "$report_directory"
elapsed_seconds=$(($(date +%s) - started_epoch))
cp "$payload/reconciliation.json" "$report_directory/reconciliation.json"
printf '{"environment":"isolated","external_writes":false,"public_ingress":false,"restore_seconds":%s}\n' "$elapsed_seconds" >"$report_directory/restore-record.json"
chmod 0600 "$report_directory/reconciliation.json" "$report_directory/restore-record.json"
echo "restore_rehearsal=passed restore_seconds=$elapsed_seconds"
