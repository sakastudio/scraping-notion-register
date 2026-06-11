import os

from flask import Flask
from threading import Thread


# ホスティングしているrenderでbotが落ちないようにするためにサーバーを開けておく
app = Flask('')

@app.route('/')
def home():
    # RENDER_GIT_COMMITはRenderが自動設定する。どのコミットが稼働中かを外部から確認できるようにする
    commit = os.environ.get("RENDER_GIT_COMMIT", "unknown")
    return f"I'm alive (commit: {commit})"

def run():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run)
    t.start()