#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Beta release entrypoint must run as root" >&2
  exit 2
fi
if [ "$#" -ne 3 ]; then
  echo "usage: release.sh deploy <manifest> <registry-user> | rollback <release-id> <reason>" >&2
  exit 2
fi

exec python /opt/nora/deploy/release.py \
  --env-file /etc/nora/production.env \
  --state-dir /var/lib/nora/releases \
  --backup-destination /mnt/private-append-only/nora \
  "$@"
