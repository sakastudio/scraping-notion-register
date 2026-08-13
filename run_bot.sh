#!/usr/bin/env bash
# scraping-notion-register bot launcher — macOS port.
# Differences vs the Linux original:
#   - no flock: single-instance enforced via the pgrep + lsof(cwd) check below
#   - no /proc: cwd resolved with `lsof -a -p PID -d cwd`
#   - PLAYWRIGHT_BROWSERS_PATH derived from the data root (no hardcoded /opt/data)
set -uo pipefail
cd "$(dirname "$0")"
APP_DIR="$PWD"
# data/repos/scraping-notion-register -> data
DATA_ROOT="$(cd "$APP_DIR/../.." && pwd)"

export PLAYWRIGHT_BROWSERS_PATH="$DATA_ROOT/.cache/ms-playwright"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

is_empty() { eval "[ -z \"\${$1-}\" ]"; }
missing=()
for k in DISCORD_BOT_TOKEN NOTION_TOKEN NOTION_DATABASE_ID FIRECRAWL_API_KEY GEMINI_API_KEY; do
  if is_empty "$k"; then
    missing+=("$k")
  fi
done
if is_empty WATCH_CHANNEL_IDS && is_empty DISCORD_CHANNEL_ID; then
  missing+=("WATCH_CHANNEL_IDS_or_DISCORD_CHANNEL_ID")
fi
if [ "${#missing[@]}" -gt 0 ]; then
  printf 'scraping-notion-register bot not started: missing env: %s\n' "${missing[*]}" >&2
  exit 1
fi

# Single-instance guard (flock replacement): bail if a discord_bot.py is already
# running with this APP_DIR as its working directory.
for pid in $(pgrep -f '[d]iscord_bot.py' 2>/dev/null || true); do
  cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
  if [ "$cwd" = "$APP_DIR" ]; then
    echo "scraping-notion-register bot is already running: pid=$pid" >&2
    exit 0
  fi
done

exec .venv/bin/python discord_bot.py
