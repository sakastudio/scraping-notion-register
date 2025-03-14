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
async def register_url(interaction: discord.Interaction, url: str):
    await interaction.response.defer(thinking=True)
    
    try:
        # URLのバリデーション（簡易版）
        if not (url.startswith('http://') or url.startswith('https://')):
            await interaction.followup.send("有効なURLを入力してください（http://またはhttps://で始まる形式）")
            return
        
        # 処理開始メッセージ
        await interaction.followup.send(f"URL `{url}` の処理を開始します...")
        
        # バックグラウンド処理のためにキューに追加
        task_queue.put({
            'type': 'register',
            'url': url,
            'interaction_id': interaction.id,
            'channel_id': interaction.channel_id
        })
        
    except Exception as e:
        await interaction.followup.send(f"エラーが発生しました: {str(e)}")

# バックグラウンド処理用のスレッド関数
def process_task_queue():
    while True:
        try:
            # キューからタスクを取得
            task = task_queue.get()
            
            if task['type'] == 'register':
                channel_id = task['channel_id']
                url = task['url']
                
                try:
                    # サイトのコンテンツを取得
                    content = fetch_and_convert_to_markdown(url)
                    if not content:
                        asyncio.run_coroutine_threadsafe(
                            bot.get_channel(channel_id).send(f"コンテンツの取得に失敗しました: {url}"),
                            bot.loop
                        )
                        continue
                    
                    # Notionテーブルに登録
                    page = register_notion_table(content, url=url)
                    
                    # 完了メッセージを送信
                    page_url = page.get("url", "不明")
                    message = f"✅ URLの登録が完了しました!\n元URL: {url}\nNotion URL: {page_url}"
                    
                    asyncio.run_coroutine_threadsafe(
                        bot.get_channel(channel_id).send(message),
                        bot.loop
                    )
                    
                except Exception as e:
                    error_message = f"処理中にエラーが発生しました: {str(e)}"
                    asyncio.run_coroutine_threadsafe(
                        bot.get_channel(channel_id).send(error_message),
                        bot.loop
                    )
            
            # タスク完了をキューに通知
            task_queue.task_done()
                
        except Exception as e:
            print(f"バックグラウンド処理でエラーが発生しました: {e}")

# バックグラウンド処理スレッドの起動
background_thread = threading.Thread(target=process_task_queue, daemon=True)
background_thread.start()

keep_alive()
bot.run(os.environ["DISCORD_BOT_TOKEN"])
