import os
import re
import asyncio
import threading
import queue
import discord
from io import BytesIO

from keep_alive import keep_alive
from get_site import fetch_and_convert_to_markdown
from get_youtube import fetch_youtube_info, extract_video_id
from article_generator import process_youtube_for_notion
from notion_table import register_notion_table
from title_translator import is_non_japanese_title, translate_title

# 設定
WATCH_CHANNEL_IDS = ["1350334310452039680"]

# URLの正規表現パターン
URL_PATTERN = r'https?://[^\s)"]+'

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

# 処理キュー
task_queue = queue.Queue()

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
    # 自分自身のメッセージは無視
    if message.author == bot.user:
        return

    # 指定されたチャンネル以外のメッセージは無視
    if not WATCH_CHANNEL_IDS or str(message.channel.id) not in WATCH_CHANNEL_IDS:
        return
        
    # メッセージからURLを抽出
    urls = re.findall(URL_PATTERN, message.content)
    
    if not urls:
        return  # URLが見つからない場合は何もしない
        
    for url in urls:
        try:
            # 処理開始メッセージ
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
            await message.channel.send(f"エラーが発生しました: {str(e)}")

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
    url = task['url']
    tags = task.get('tags')  # タグは省略可能

    try:
        # YouTube URLかどうかチェック
        if is_youtube_url(url):
            # YouTube動画の処理
            status_msg = f"YouTube動画の情報を取得しています..."
            send_discord_message(channel_id, status_msg)
            
            # 動画情報と字幕を取得（Discord送信関数を渡す）
            def youtube_log_sender(msg):
                send_discord_message(channel_id, f"🔍 {msg}")
            
            title, description, transcript, metadata = fetch_youtube_info(
                url, 
                send_message_func=youtube_log_sender
            )
            if not title:
                send_discord_message(channel_id, f"❌ YouTube動画の情報取得に失敗しました: {url}")
                return
            
            # 字幕から記事を生成
            status_msg = f"字幕から記事を生成しています..."
            send_discord_message(channel_id, status_msg)
            
            # 記事生成と字幕の結合
            content = process_youtube_for_notion(
                title=title,
                description=description,
                transcript=transcript,
                url=url,
                metadata=metadata
            )
        else:
            # 通常のWebページの処理
            status_msg = f"サイトのコンテンツを取得しています..."
            send_discord_message(channel_id, status_msg)
            # サイトのタイトルとコンテンツを取得
            title, content = fetch_and_convert_to_markdown(url)
        if not content:
            send_discord_message(channel_id, f"❌ コンテンツの取得に失敗しました: {url}")
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

    except Exception as e:
        # 例外発生箇所のファイル名と行番号を付けて通知
        try:
            import traceback
            tb = traceback.extract_tb(e.__traceback__)
            if tb:
                filename, lineno, _, _ = tb[-1]
                error_message = f"❌ 処理中にエラーが発生しました: {str(e)} (ファイル: {filename}, 行: {lineno})"
            else:
                error_message = f"❌ 処理中にエラーが発生しました: {str(e)}"
        except Exception as _:
            error_message = f"❌ 処理中にエラーが発生しました: {str(e)}"
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
    # 必要なライブラリのインポート
    import time
    
    print("Discord Bot を起動中...")
    print(f"監視対象チャンネル: {WATCH_CHANNEL_IDS if WATCH_CHANNEL_IDS else '未設定'}")
    
    # バックグラウンド処理スレッドの起動
    background_thread = threading.Thread(target=process_task_queue, daemon=True)
    background_thread.start()
    
    # Webサーバー起動（Replit用）
    keep_alive()
    
    # Botの実行
    bot.run(os.environ.get("DISCORD_BOT_TOKEN"))
