from flask import Flask, render_template, make_response
from datetime import datetime
from zoneinfo import ZoneInfo
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

    updated_at = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")

    response = make_response(render_template(
        "index.html",
        news_list=news_list,
        updated_at=updated_at
    ))

    # 브라우저 캐시 방지: 새로고침 시 updated_at이 실제로 갱신되도록 설정
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
