import os
import asyncio
import threading
import queue
from discord import app_commands
import discord
from io import BytesIO

from keep_alive import keep_alive

intents = discord.Intents.default()
intents.message_content = True  # メッセージの内容を取得する権限

# Botをインスタンス化
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    await tree.sync()
    print("Bot is ready!")


keep_alive()
bot.run(os.environ["DISCORD_BOT_TOKEN"])
