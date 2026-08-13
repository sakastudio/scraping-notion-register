# YouTube Codex Notion Import Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** `https://m.youtube.com/watch?v=mcn6Q-LAgTQ`を含むYouTube URLをDiscord Botが取得し、ChatGPTサブスク認証のCodexで記事化して、動画情報・記事・検索可能な全文字幕をNotionへ登録する。

**Architecture:** YouTube URLを動画ID基準でcanonical化し、専用取得器が字幕とmetadataを完全取得する。記事生成はCodex CLIアダプターへ分離し、stdin入力・ephemeral/read-only実行・一時出力検証を行う。記事と未加工全文字幕をアプリ側で安全に結合して既存Notion登録器へ渡す。

**Tech Stack:** Python 3.12, unittest, yt-dlp/YouTube public transcript surfaces, Codex CLI ChatGPT auth, Notion API, Discord.py.

---

### Task 1: Canonical YouTube URLs

**Files:**
- Modify: `url_preprocessor.py`
- Modify: `get_youtube.py`
- Test: `tests/test_youtube_import.py`

1. RED: mobile/watch, youtu.be, shorts, embed variants map to `https://www.youtube.com/watch?v=<id>`; reject deceptive hosts and invalid IDs.
2. Run focused test and confirm expected failure.
3. Implement parser-based video ID extraction and canonicalization.
4. Run focused and full tests.

### Task 2: Reliable Metadata and Full Transcript Retrieval

**Files:**
- Modify: `get_youtube.py`
- Test: `tests/test_youtube_import.py`

1. RED: enforce manual-ja → auto-ja → manual-en → auto-en, preserve full transcript, record language/manual status, avoid stale cookie forcing, and sanitize errors.
2. Reproduce the target video's current login failure.
3. Implement minimal reliable retrieval using yt-dlp public clients and/or the reference extension's public InnerTube/transcript strategy. Use cookies only when valid/needed; never log values.
4. Verify fixtures and live target video return title, metadata, and non-empty full transcript.

### Task 3: Codex ChatGPT-Auth Article Adapter

**Files:**
- Rewrite: `article_generator.py`
- Test: `tests/test_youtube_import.py`

1. RED with fake executable: prompt arrives only via stdin; argv excludes transcript/secrets; HOME/CODEX_HOME are explicit; execution is ephemeral/read-only; output is validated; temp files cleaned on success/failure/timeout.
2. Implement `generate_article_with_codex` with configurable absolute binary/home/model/timeout and safe default authenticated home.
3. Build a prompt based on the reference extension, with prompt-injection boundaries and Japanese Markdown-only output.
4. Smoke-test live Codex auth without exposing auth data.

### Task 4: Searchable Full Transcript Content

**Files:**
- Modify: `article_generator.py`
- Modify: `notion_table.py` only if needed for a safe plaintext boundary
- Test: `tests/test_youtube_import.py`

1. RED: generated article plus video metadata plus every transcript character appears; transcript becomes paragraph blocks, not code/image/file blocks; hostile Markdown-like transcript cannot inject blocks.
2. Implement a trusted application-owned transcript section and lossless chunking under Notion limits.
3. Run focused/full tests.

### Task 5: Discord Worker Integration and Atomic Failure

**Files:**
- Modify: `discord_bot.py`
- Test: `tests/test_youtube_import.py`

1. RED: YouTube no longer emits SKIPPED; it reports acquisition/article progress and calls Notion only after transcript and article validation; failure never calls Notion.
2. Implement the dedicated branch and useful redacted errors.
3. Verify canonical URL is used for duplicate detection and completion output.
4. Run full tests, py_compile, diff check.

### Task 6: Target-Video E2E, Review, and Deployment

1. Run target URL through metadata/transcript retrieval.
2. Generate the real article with ChatGPT-authenticated Codex.
3. Register into the configured Notion database.
4. Read the page back through Notion API and verify URL, title, article headings, metadata, and transcript beginning/middle/end in normal paragraph blocks.
5. Run independent security/correctness/operations reviews; fix Critical/High findings with regression tests and rerun review.
6. Run all tests and checks; commit implementation; push `main`.
7. Restart via the existing watchdog, verify exactly one new Bot PID, health response, and ready/channel logs.
