from flask import Flask, render_template, make_response, abort
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import os
import re

app = Flask(__name__)

ARCHIVE_DIR = os.path.join("data", "archive")
ARCHIVE_INDEX_PATH = os.path.join(ARCHIVE_DIR, "index.json")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


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

    return no_cache(response)


@app.route("/archive")
def archive_list():
    dates = []

    if os.path.exists(ARCHIVE_INDEX_PATH):
        with open(ARCHIVE_INDEX_PATH, "r", encoding="utf-8") as f:
            dates = json.load(f)

    response = make_response(render_template("archive_list.html", dates=dates))
    return no_cache(response)


@app.route("/archive/<date>")
def archive_day(date):
    if not DATE_PATTERN.match(date):
        abort(404)

    day_path = os.path.join(ARCHIVE_DIR, f"{date}.json")

    if not os.path.exists(day_path):
        news_list = []
    else:
        with open(day_path, "r", encoding="utf-8") as f:
            news_list = json.load(f)

        for item in news_list:
            published_at = item.get("published_at")
            label = ""

            if published_at:
                try:
                    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    dt = dt.astimezone(ZoneInfo("Asia/Seoul"))
                    label = dt.strftime("%H:%M")
                except Exception:
                    label = ""

            item["published_time_label"] = label

    response = make_response(render_template(
        "archive_day.html",
        date=date,
        news_list=news_list
    ))

    return no_cache(response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
