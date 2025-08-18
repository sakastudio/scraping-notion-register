# Repository Guidelines

This repository hosts a small Python toolchain and Discord bot that scrapes shared URLs, converts content to Markdown (Firecrawl), predicts tags (OpenAI), and registers entries into a Notion database.

## Project Structure & Module Organization
- `discord_bot.py`: Entry point. Watches channels, queues work, posts status.
- `get_site.py`: Fetches a URL and returns `(title, markdown)`; writes to `downloaded/output.md` in its demo.
- `notion_table.py`: Creates a Notion page and uploads Markdown as blocks.
- `tag_predictor.py`: Loads `tags.txt` and predicts tags via OpenAI.
- `title_translator.py`: Optional title translation using OpenAI.
- `keep_alive.py`: Lightweight Flask server for uptime pings.
- `start.sh`: Installs deps and runs the bot.
- Data/assets: `tags.txt`, `url_list.txt`, `cookies.json`; output: `downloaded/`.

## Build, Test, and Development Commands
- Create env and install: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Run bot (recommended): `bash start.sh` or `python3 discord_bot.py`
- Local scrape test: `python3 get_site.py` (writes `downloaded/output.md`)
- Notion upload test (requires env): `python3 notion_table.py` (uses `downloaded/output.md` in its demo)

Required env vars (example):
```
export FIRECRAWL_API_KEY=... 
export OPENAI_API_KEY=...
export NOTION_TOKEN=...
export DISCORD_BOT_TOKEN=...
```

## Coding Style & Naming Conventions
- Python 3.x, PEP 8, 4‑space indentation; prefer type hints (see `notion_table.py`).
- Filenames: `lower_snake_case.py`; functions/variables: `lower_snake_case`; constants: `UPPER_SNAKE`.
- Keep modules single‑purpose; guard runnable demos with `if __name__ == "__main__":`.

## Testing Guidelines
- No formal test suite. Prefer smoke tests via module `__main__` blocks (`get_site.py`, `notion_table.py`).
- If you add tests, use `pytest`, name files `tests/test_*.py`, and keep tests fast and isolated.

## Commit & Pull Request Guidelines
- Commits: short, imperative; Japanese OK. Include scope when helpful.
  - Example: `get_site: クッキー処理を簡素化` or `notion: fix block batching`.
- PRs: clear description, linked issues, affected configs/env, and before/after behavior. Include logs or screenshots of successful runs where relevant.

## Security & Configuration Tips
- Never commit tokens or `cookies.json`. Use `.env` (loaded by `python-dotenv`) or exported env vars.
- Update `WATCH_CHANNEL_IDS` in `discord_bot.py` for target channels. Notion Database ID is set in `notion_table.py`; adjust before deploy.
