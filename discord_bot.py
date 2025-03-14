import os
import asyncio
import threading
import queue
from discord import app_commands
import discord
from io import BytesIO

from keep_alive import keep_alive
from get_site import fetch_and_convert_to_markdown
from notion_table import register_notion_table

# 処理キュー
task_queue = queue.Queue()

intents = discord.Intents.default()
intents.message_content = True  # メッセージの内容を取得する権限

# Botをインスタンス化
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    await tree.sync()
    print("Bot is ready!")

# URLの登録コマンド
@tree.command(name="register_url", description="指定したURLのコンテンツをNotionテーブルに登録します")
@app_commands.describe(
    url="登録するWebページのURL",
    tags="カンマ区切りのタグリスト（例: ニュース,テクノロジー,AI）、指定しない場合は自動予測"
)
async def register_url(interaction: discord.Interaction, url: str, tags: str = None):
    await interaction.response.defer(thinking=True)
    
    try:
        # URLのバリデーション（簡易版）
        if not (url.startswith('http://') or url.startswith('https://')):
            await interaction.followup.send("有効なURLを入力してください（http://またはhttps://で始まる形式）")
            return
        
        # タグの処理
        tag_list = None
        if tags:
            # カンマ区切りのタグをリストに変換
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
            tag_msg = f"指定されたタグ: {', '.join(tag_list)}"
        else:
            tag_msg = "タグは自動予測されます"
        
        # 処理開始メッセージ
        await interaction.followup.send(f"URL `{url}` の処理を開始します...\n{tag_msg}")
        
        # バックグラウンド処理のためにキューに追加
        task_queue.put({
            'type': 'register',
            'url': url,
            'tags': tag_list,
            'interaction_id': interaction.id,
            'channel_id': interaction.channel_id
        })
        
    except Exception as e:
        await interaction.followup.send(f"エラーが発生しました: {str(e)}")

# Discord チャンネルにメッセージを送信するヘルパー関数
def send_discord_message(channel_id, message):
    """Discord チャンネルにメッセージを送信する"""
    try:
        asyncio.run_coroutine_threadsafe(
            bot.get_channel(channel_id).send(message),
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
        # サイトのタイトルとコンテンツを取得
        title, content = fetch_and_convert_to_markdown(url)
        if not content:
            send_discord_message(channel_id, f"コンテンツの取得に失敗しました: {url}")
            return
        
        # Notionテーブルに登録
        page = register_notion_table(content, url=url, title=title, tags=tags)
        
        # 完了メッセージを送信
        page_url = page.get("url", "不明")
        
        # タグ情報を追加
        if tags:
            tag_info = f"タグ: {', '.join(tags)}"
        else:
            # 自動予測されたタグの情報を取得（簡易版）
            tag_info = "タグ: 自動予測"
            
        message = f"✅ URLの登録が完了しました!\n元URL: {url}\nNotion URL: {page_url}\n{tag_info}"
        send_discord_message(channel_id, message)
            
    except Exception as e:
        error_message = f"処理中にエラーが発生しました: {str(e)}"
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
                
        except Exception as e:
            print(f"バックグラウンド処理でエラーが発生しました: {e}")

# バックグラウンド処理スレッドの起動
background_thread = threading.Thread(target=process_task_queue, daemon=True)
background_thread.start()

keep_alive()
bot.run(os.environ["DISCORD_BOT_TOKEN"])
