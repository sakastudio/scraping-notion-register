import os
import re
import asyncio
import threading
import queue
import time
import json
import sys
import traceback
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlparse

import discord
from io import BytesIO

from keep_alive import keep_alive
from get_site import fetch_and_convert_to_markdown
from get_youtube import fetch_youtube_info, extract_video_id
from article_generator import process_youtube_for_notion
from get_x_post import fetch_x_post
from get_x_article import fetch_x_article, is_x_article_url
from notion_table import register_notion_table
from title_translator import is_non_japanese_title, translate_title
from url_preprocessor import normalize_registration_url

# 設定
# WATCH_CHANNEL_IDS: カンマ区切り複数指定可。後方互換として DISCORD_CHANNEL_ID も読む。
_watch_channel_ids_env = os.environ.get("WATCH_CHANNEL_IDS") or os.environ.get("DISCORD_CHANNEL_ID", "")
WATCH_CHANNEL_IDS = [channel_id.strip() for channel_id in _watch_channel_ids_env.split(",") if channel_id.strip()]

# URLの正規表現パターン
URL_PATTERN = r'https?://[^\s)"]+'
DISCORD_MESSAGE_LIMIT = 2000
URL_LOG_PREFIX = "URL_EVENT"


class UrlEvent(StrEnum):
    DETECTED = "detected"
    ENQUEUE_FAILED = "enqueue_failed"
    PROCESSING_STARTED = "processing_started"
    SKIPPED_YOUTUBE = "skipped_youtube"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    PROCESSING_FAILED = "processing_failed"
    COMPLETED = "completed"


def log_url_event(event: UrlEvent, *, url, raw_url=None, channel_id=None, message_id=None, error=None, stream=None):
    """URL処理イベントをbot.logで検索しやすい1行JSONとして記録する。"""
    payload = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "event": event.value,
        "url": url,
    }
    if raw_url is not None:
        payload["raw_url"] = raw_url
    if channel_id is not None:
        payload["channel_id"] = str(channel_id)
    if message_id is not None:
        payload["message_id"] = str(message_id)
    if error is not None:
        payload["error"] = str(error)

    output = stream if stream is not None else sys.stdout
    print(URL_LOG_PREFIX + " " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=output, flush=True)


def format_url_error_message(summary, url, error, *, location=None):
    """Discordの上限内で、対象URLを必ずプレーンテキストで残す。"""
    location_line = f"\n発生箇所: {location}" if location else ""
    suffix = f"{location_line}\n対象URL:\n{url}"
    prefix = f"❌ {summary}: "
    error_text = str(error)
    available = DISCORD_MESSAGE_LIMIT - len(prefix) - len(suffix)
    if available < 0:
        suffix = f"\n対象URL:\n{url[: max(0, DISCORD_MESSAGE_LIMIT - len(prefix) - 20)]}"
        available = DISCORD_MESSAGE_LIMIT - len(prefix) - len(suffix)
    if len(error_text) > available:
        error_text = error_text[: max(0, available - 1)] + "…"
    return prefix + error_text + suffix

# YouTube URLの判定関数
def is_youtube_url(url: str) -> bool:
    """YouTube URLかどうかを判定"""
    youtube_domains = [
        'youtube.com',
        'youtu.be',
        'www.youtube.com',
        'm.youtube.com'
    ]
    return any(domain in url.lower() for domain in youtube_domains)

# X/Twitter URLの判定関数
def is_x_url(url: str) -> bool:
    """X/Twitter URLかどうかを判定"""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        x_domains = ['x.com', 'twitter.com', 'www.x.com', 'www.twitter.com', 'mobile.twitter.com']
        return hostname in x_domains
    except Exception:
        return False

# 処理キュー
task_queue = queue.Queue()

# 同じサイトへの連続アクセスを避けるためのクールダウン。
# RedditのようにURL単位ではなくホスト単位で制限されるサイトに合わせ、
# www/old/new/mobile などのサブドメイン差は同一ホストキーとして扱う。
def _parse_url_cooldown_seconds(raw_value: str | None, default: float = 60.0) -> float:
    try:
        value = float(raw_value if raw_value is not None else default)
    except (TypeError, ValueError):
        return default
    if value != value or value < 0 or value > 3600:
        return default
    return value


URL_COOLDOWN_SECONDS = _parse_url_cooldown_seconds(os.environ.get("URL_COOLDOWN_SECONDS"))
_url_last_processed_at = {}
_url_cooldown_lock = threading.Lock()


def _url_cooldown_key(url: str) -> str:
    try:
        hostname = (urlparse(url).hostname or "").lower()
    except Exception:
        return url.strip().lower()

    if hostname == "redd.it" or hostname.endswith(".reddit.com") or hostname == "reddit.com":
        return "reddit.com"

    for prefix in ("www.", "old.", "new.", "mobile.", "m."):
        if hostname.startswith(prefix):
            hostname = hostname[len(prefix):]
            break
    return hostname or url.strip().lower()


def wait_for_url_cooldown(url: str, now_fn=time.monotonic, sleep_fn=time.sleep, before_sleep_fn=None) -> float:
    """同じサイトへの処理開始間隔をURL_COOLDOWN_SECONDS以上にする。"""
    key = _url_cooldown_key(url)
    slept = 0.0

    while True:
        with _url_cooldown_lock:
            now = now_fn()
            last_started_at = _url_last_processed_at.get(key)
            if last_started_at is None:
                _url_last_processed_at[key] = now
                return slept

            wait_seconds = URL_COOLDOWN_SECONDS - (now - last_started_at)
            if wait_seconds <= 0:
                _url_last_processed_at[key] = now
                return slept

        if before_sleep_fn:
            before_sleep_fn(wait_seconds)
        sleep_fn(wait_seconds)
        slept += wait_seconds


# 同一メッセージ内で既に取得済みのXポストIDを追跡（重複登録防止）
# key: message_id, value: set of post IDs
_message_processed_x_ids = {}

intents = discord.Intents.default()
intents.message_content = True  # メッセージの内容を取得する権限

# Botをインスタンス化
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print("Bot is ready!")
    
    # 監視対象チャンネルの情報を表示
    if WATCH_CHANNEL_IDS:
        print(f"以下のチャンネルを監視します:")
        for channel_id in WATCH_CHANNEL_IDS:
            channel = bot.get_channel(int(channel_id.strip()))
            channel_name = channel.name if channel else "不明"
            print(f" - {channel_id} ({channel_name})")
    else:
        print("警告: 監視対象のチャンネルが設定されていません。WATCH_CHANNEL_IDS環境変数を設定してください。")

@bot.event
async def on_message(message):
    # Bot / Webhook 由来のメッセージは無視（Notion uploader bot からの通知にも反応しない）
    if message.author == bot.user or getattr(message.author, "bot", False) or message.webhook_id is not None:
        return

    # 指定されたチャンネル以外のメッセージは無視
    if not WATCH_CHANNEL_IDS or str(message.channel.id) not in WATCH_CHANNEL_IDS:
        return
        
    # メッセージからURLを抽出
    urls = re.findall(URL_PATTERN, message.content)
    
    if not urls:
        return  # URLが見つからない場合は何もしない
        
    for raw_url in urls:
        try:
            url = normalize_registration_url(raw_url)
            log_url_event(
                UrlEvent.DETECTED,
                raw_url=raw_url,
                url=url,
                channel_id=message.channel.id,
                message_id=message.id,
            )
            # 処理開始メッセージ
            if url != raw_url:
                response = await message.channel.send(f"URL `{raw_url}` を検出しました。登録URLを `{url}` に正規化して処理を開始します...")
            else:
                response = await message.channel.send(f"URL `{url}` を検出しました。処理を開始します...")
            
            # バックグラウンド処理のためにキューに追加
            task_queue.put({
                'type': 'register',
                'url': url,
                'tags': None,  # 自動予測
                'message_id': message.id,
                'channel_id': message.channel.id
            })
            
        except Exception as e:
            log_url_event(
                UrlEvent.ENQUEUE_FAILED,
                raw_url=raw_url,
                url=raw_url,
                channel_id=message.channel.id,
                message_id=message.id,
                error=e,
            )
            await message.channel.send(format_url_error_message("URL受付中にエラーが発生しました", raw_url, e))

# Discord チャンネルにメッセージを送信するヘルパー関数
def send_discord_message(channel_id, message):
    """Discord チャンネルにメッセージを送信する"""
    try:
        asyncio.run_coroutine_threadsafe(
            bot.get_channel(int(channel_id)).send(message),
            bot.loop
        )
    except Exception as e:
        print(f"メッセージ送信中にエラーが発生: {e}")

# URL登録タスクの処理関数
def process_register_task(task):
    """URLを取得してNotionに登録するタスク処理"""
    channel_id = task['channel_id']
    url = normalize_registration_url(task['url'])
    tags = task.get('tags')  # タグは省略可能

    log_url_event(
        UrlEvent.PROCESSING_STARTED,
        url=url,
        channel_id=channel_id,
        message_id=task.get('message_id'),
    )

    try:
        def notify_cooldown(wait_seconds):
            send_discord_message(
                channel_id,
                f"同じサイトへの連続アクセスを避けるため、約{wait_seconds:.0f}秒後に処理します。"
            )

        # YouTube URLかどうかチェック
        if is_youtube_url(url):
            send_discord_message(channel_id, "YouTube動画を検出しました。記事生成はChrome拡張を使ってください。")
            log_url_event(UrlEvent.SKIPPED_YOUTUBE, url=url, channel_id=channel_id, message_id=task.get('message_id'))
            return
        elif is_x_article_url(url):
            waited = wait_for_url_cooldown(url, before_sleep_fn=notify_cooldown)
            # X/Twitter記事（Article）の処理
            send_discord_message(channel_id, "X/Twitterの記事（Article）を取得しています...")
            title, content = fetch_x_article(url)
        elif is_x_url(url):
            # 同一メッセージ内で既に取得済みのポストIDかチェック
            post_id_match = re.search(r'/status/(\d+)', url)
            msg_id = task.get('message_id')
            if post_id_match and msg_id:
                post_id = post_id_match.group(1)
                if msg_id in _message_processed_x_ids and post_id in _message_processed_x_ids[msg_id]:
                    send_discord_message(channel_id, f"ポスト `{url}` は引用ツイートとして既に登録済みのためスキップします。")
                    log_url_event(UrlEvent.SKIPPED_DUPLICATE, url=url, channel_id=channel_id, message_id=msg_id)
                    return

            # X/Twitterポストの処理
            waited = wait_for_url_cooldown(url, before_sleep_fn=notify_cooldown)
            send_discord_message(channel_id, "X/Twitterのポストを取得しています...")
            title, content, collected_ids = fetch_x_post(url)

            # 取得した全ポストIDを記録（同一メッセージの後続タスクで重複防止）
            if msg_id and collected_ids:
                if msg_id not in _message_processed_x_ids:
                    _message_processed_x_ids[msg_id] = set()
                _message_processed_x_ids[msg_id].update(collected_ids)
        else:
            # 通常のWebページの処理
            waited = wait_for_url_cooldown(url, before_sleep_fn=notify_cooldown)
            status_msg = f"サイトのコンテンツを取得しています..."
            send_discord_message(channel_id, status_msg)
            # サイトのタイトルとコンテンツを取得
            title, content = fetch_and_convert_to_markdown(url)

        if not content:
            error = RuntimeError("コンテンツが空でした")
            log_url_event(UrlEvent.PROCESSING_FAILED, url=url, channel_id=channel_id, message_id=task.get('message_id'), error=error)
            send_discord_message(channel_id, format_url_error_message("コンテンツの取得に失敗しました", url, error))
            return

        # タイトルの翻訳（英語など日本語以外の場合）
        original_title = title
        translated_title = None

        if is_non_japanese_title(title):
            status_msg = f"タイトルを翻訳しています..."
            send_discord_message(channel_id, status_msg)

            translated_title = translate_title(title)
            if translated_title:
                title = f"{translated_title} (原題: {original_title})"

        # 処理状況の更新
        status_msg = f"Notionテーブルに登録しています..."
        send_discord_message(channel_id, status_msg)

        # Notionテーブルに登録
        page = register_notion_table(content, url=url, title=title, tags=tags)

        # 完了メッセージを送信
        page_url = page.get("url", "不明")

        # タグ情報を取得
        try:
            # 登録されたタグの取得を試みる（存在すれば）
            registered_tags = []
            if "properties" in page and "タグ" in page["properties"] and "multi_select" in page["properties"]["タグ"]:
                for tag_obj in page["properties"]["タグ"]["multi_select"]:
                    if "name" in tag_obj:
                        registered_tags.append(tag_obj["name"])

            if registered_tags:
                tag_info = f"タグ: {', '.join(registered_tags)}"
            else:
                tag_info = "タグ: なし"
        except:
            # エラーが発生した場合はシンプルな情報を表示
            if tags:
                tag_info = f"タグ: {', '.join(tags)}"
            else:
                tag_info = "タグ: 自動予測（詳細不明）"

        # 翻訳情報を表示用に整形
        title_info = title
        if translated_title:  # 翻訳された場合
            title_info = f"**タイトル:** {translated_title}\n**原題:** {original_title}"
        else:
            title_info = f"**タイトル:** {title}"

        message = f"✅ URLの登録が完了しました!\n{title_info}\n**元URL:** {url}\n**Notion URL:** {page_url}\n**{tag_info}**"
        send_discord_message(channel_id, message)
        log_url_event(UrlEvent.COMPLETED, url=url, channel_id=channel_id, message_id=task.get('message_id'))

    except Exception as e:
        # 例外箇所とURLを通知・記録
        try:
            tb = traceback.extract_tb(e.__traceback__)
            if tb:
                filename, lineno, _, _ = tb[-1]
                location = f"{filename}:{lineno}"
                error_message = format_url_error_message(
                    "処理中にエラーが発生しました",
                    url,
                    e,
                    location=location,
                )
            else:
                error_message = format_url_error_message("処理中にエラーが発生しました", url, e)
        except Exception:
            error_message = format_url_error_message("処理中にエラーが発生しました", url, e)
        log_url_event(
            UrlEvent.PROCESSING_FAILED,
            url=url,
            channel_id=channel_id,
            message_id=task.get('message_id'),
            error=e,
        )
        traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
        send_discord_message(channel_id, error_message)


# バックグラウンド処理用のスレッド関数
def process_task_queue():
    """キューからタスクを取得して処理する"""
    while True:
        try:
            # キューからタスクを取得
            task = task_queue.get()
            
            # タスクタイプに応じて適切な処理関数を呼び出す
            if task['type'] == 'register':
                process_register_task(task)
            else:
                print(f"不明なタスクタイプ: {task['type']}")
            
            # タスク完了をキューに通知
            task_queue.task_done()
            
            # 次のタスクまで少し待機（API制限対策）
            time.sleep(1)
                
        except Exception as e:
            print(f"バックグラウンド処理でエラーが発生しました: {e}")
            # エラーが発生しても継続するために少し待機
            time.sleep(5)

if __name__ == "__main__":
    print("Discord Bot を起動中...")
    print(f"監視対象チャンネル: {WATCH_CHANNEL_IDS if WATCH_CHANNEL_IDS else '未設定'}")

    # バックグラウンド処理スレッドの起動
    background_thread = threading.Thread(target=process_task_queue, daemon=True)
    background_thread.start()
    
    # Webサーバー起動（Replit用）
    keep_alive()
    
    # Botの実行
    bot.run(os.environ.get("DISCORD_BOT_TOKEN"))
