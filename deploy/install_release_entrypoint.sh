#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: install_release_entrypoint.sh <dedicated-runner-user>" >&2
  exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "release entrypoint installation must run as root" >&2
  exit 2
fi

runner_user=$1
case "$runner_user" in
  *[!a-zA-Z0-9_-]*|'') echo "runner user is invalid" >&2; exit 2 ;;
esac
id "$runner_user" >/dev/null
command -v docker >/dev/null
command -v gh >/dev/null
command -v visudo >/dev/null

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -d -o root -g root -m 0755 /opt/nora/deploy
for name in compose.production.yml preflight.py public_smoke.py release.py release_manifest.py \
  verify_release_ci.py verify_release_control.py
do
  install -o root -g root -m 0644 "$script_dir/$name" "/opt/nora/deploy/$name"
done
install -o root -g root -m 0755 "$script_dir/backup.sh" /opt/nora/deploy/backup.sh
install -o root -g root -m 0755 "$script_dir/release.sh" /usr/local/sbin/nora-release
install -d -o root -g root -m 0700 /var/lib/nora/releases

sudoers=/etc/sudoers.d/nora-release
temporary=$(mktemp /etc/sudoers.d/.nora-release.XXXXXX)
cleanup() {
  if [ -n "${temporary:-}" ] && [ -e "$temporary" ]; then
    unlink "$temporary"
  fi
}
trap cleanup EXIT HUP INT TERM
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/nora-release deploy *, /usr/local/sbin/nora-release rollback *\n' \
  "$runner_user" >"$temporary"
chmod 0440 "$temporary"
chown root:root "$temporary"
visudo -cf "$temporary"
mv "$temporary" "$sudoers"
temporary=
echo "release_entrypoint=installed runner_user=$runner_user"
