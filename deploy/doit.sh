#!/bin/bash
git pull && uv run manage.py migrate && uv run manage.py collectstatic --noinput && sudo systemctl restart zingor
