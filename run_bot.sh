#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PLAYWRIGHT_BROWSERS_PATH=/opt/data/.cache/ms-playwright
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
exec .venv/bin/python discord_bot.py
