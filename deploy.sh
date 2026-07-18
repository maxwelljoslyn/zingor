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
  git fetch --tags origin
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
sudo systemctl restart zingor.service
sudo systemctl restart zingor-huey.service
