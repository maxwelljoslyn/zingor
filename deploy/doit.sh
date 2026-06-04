#!/bin/bash
git pull && uv sync && uv run manage.py migrate && uv run manage.py collectstatic --noinput && sudo systemctl restart zingor
