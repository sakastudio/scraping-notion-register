#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# パッケージをインストール
if .venv/bin/python -m pip --version >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
elif command -v uv >/dev/null 2>&1; then
  uv pip install --python .venv/bin/python -r requirements.txt
else
  echo "pip module is missing in .venv and uv is not installed; cannot install requirements" >&2
  exit 1
fi

# Playwrightブラウザのインストール
DATA_ROOT="$(cd ../.. && pwd)"
export PLAYWRIGHT_BROWSERS_PATH="$DATA_ROOT/.cache/ms-playwright"
if ! compgen -G "$PLAYWRIGHT_BROWSERS_PATH/chromium-*/INSTALLATION_COMPLETE" >/dev/null; then
  .venv/bin/python -m playwright install chromium
fi

# Pythonファイルを実行（run_bot.sh側で単一インスタンスロックを取得）
exec ./run_bot.sh
