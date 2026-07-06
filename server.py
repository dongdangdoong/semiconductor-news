from flask import Flask, render_template
from datetime import datetime
import json
import os

app = Flask(__name__)

@app.route("/")
def index():
    news_path = os.path.join("data", "news.json")

    if os.path.exists(news_path):
        with open(news_path, "r", encoding="utf-8") as f:
            news_list = json.load(f)
    else:
        news_list = []

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return render_template(
        "index.html",
        news_list=news_list,
        updated_at=updated_at
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
