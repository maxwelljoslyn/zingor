#!/usr/bin/env bash
# Deploy the production Django app at a given git ref (default:
# origin/master; the deploy workflow passes the tag name for version
# releases): fetch, check out exactly that ref, install deps from the
# lockfile, apply migrations, refresh collected static (Caddy serves it
# from staticfiles/), then restart gunicorn. Checks out first and
# re-execs itself so the freshly checked-out version of this script is
# what runs the deploy steps.
set -euo pipefail

cd /home/maxwell/zingor

if [[ "${1:-}" != "--no-pull" ]]; then
  REF="${1:-origin/master}"
  # --force lets a release tag that moved on the remote overwrite the copy
  # already here. Without it git refuses the tag ("would clobber existing
  # tag") and exits nonzero, which set -e turns into a failed deploy -- and
  # not only for the moved tag: one rejected tag fails the whole fetch, so
  # every later deploy breaks too until the stale tag is cleared by hand.
  # This is separate from the checkout --force below, which forces past
  # working-tree edits rather than ref conflicts.
  git fetch --tags --force origin
  # --detach handles branches, tags, and remote-tracking refs uniformly;
  # every deploy starts with a fresh checkout, so detached HEAD is fine.
  # --force discards server-local edits to tracked files, which would
  # have broken the old git pull anyway.
  git checkout --force --detach "$REF"
  exec ./deploy.sh --no-pull
fi

uv sync --frozen
uv run python manage.py migrate --noinput
uv run python manage.py collectstatic --noinput

# Install version-controlled systemd unit changes from ops/. Copy only when the
# installed unit differs, so an unchanged deploy skips the daemon-reload. These
# units carry no secrets (config comes from .env via load_dotenv), so
# overwriting the installed copy never clobbers server-only state. Installed
# units are world-readable, so cmp needs no sudo; only cp and daemon-reload do.
units_changed=0
for unit in zingor.service zingor-huey.service; do
  if ! cmp -s "/home/maxwell/zingor/ops/$unit" "/etc/systemd/system/$unit"; then
    sudo cp "/home/maxwell/zingor/ops/$unit" "/etc/systemd/system/$unit"
    echo "updated $unit"
    units_changed=1
  fi
done
if [[ "$units_changed" == 1 ]]; then
  sudo systemctl daemon-reload
fi

sudo systemctl restart zingor.service
sudo systemctl restart zingor-huey.service
