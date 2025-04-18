from flask import Flask
from threading import Thread

app = Flask('')


@app.route('/')
def home():
    return "I'm alive!"


def keep_alive():
    thread = Thread(target=lambda: app.run(host='0.0.0.0', port=8081))
    thread.start()
