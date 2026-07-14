#!/usr/bin/env bash
# Deploy the production Django app: pull, install deps from the lockfile,
# apply migrations, refresh collected static (Caddy serves it from
# staticfiles/), then restart gunicorn. Pulls first and re-execs itself so
# the freshly pulled version of this script is what runs the deploy steps.
set -euo pipefail

cd /home/maxwell/zingor

if [[ "${1:-}" != "--no-pull" ]]; then
  git pull
  exec ./deploy.sh --no-pull
fi

uv sync --frozen
uv run python manage.py migrate --noinput
uv run python manage.py collectstatic --noinput
sudo systemctl restart zingor.service
sudo systemctl restart zingor-huey.service
