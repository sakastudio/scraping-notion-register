from flask import Flask
from threading import Thread


# ホスティングしているrenderでbotが落ちないようにするためにサーバーを開けておく
app = Flask('')

@app.route('/')
def home():
    return "I'm alive"

def run():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run)
    t.start()