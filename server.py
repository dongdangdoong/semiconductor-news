from flask import Flask, render_template
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from urllib.parse import quote
from datetime import datetime, timedelta
import re
import time

app = Flask(__name__)

KEYWORDS = [
    "반도체",
    "삼성전자 반도체",
    "SK하이닉스",
    "HBM",
    "DRAM",
    "NAND",
    "AI 반도체",
    "파운드리",
    "TSMC",
    "마이크론"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def summarize_text(text, min_len=100, max_len=200):
    text = clean_text(text)

    if len(text) <= max_len:
        return text

    sentences = re.split(r"(?<=[.!?。！？다])\s+", text)

    summary = ""
    for sentence in sentences:
        if len(summary) + len(sentence) <= max_len:
            summary += sentence + " "
        if len(summary) >= min_len:
            break

    summary = clean_text(summary)

    if len(summary) < min_len:
        summary = text[:max_len]

    return summary[:max_len].strip()


def parse_naver_time(time_text):
    now = datetime.now()

    if "분 전" in time_text:
        minutes = int(re.sub(r"[^0-9]", "", time_text))
        published = now - timedelta(minutes=minutes)
    elif "시간 전" in time_text:
        hours = int(re.sub(r"[^0-9]", "", time_text))
        published = now - timedelta(hours=hours)
    elif "일 전" in time_text:
        days = int(re.sub(r"[^0-9]", "", time_text))
        published = now - timedelta(days=days)
    else:
        published = now

    diff = now - published

    if diff.total_seconds() < 3600:
        return f"{int(diff.total_seconds() // 60)}분 전"
    elif diff.total_seconds() < 86400:
        return f"{int(diff.total_seconds() // 3600)}시간 전"
    else:
        return f"{diff.days}일 전"


def get_article_body(url):
    try:
        article = Article(url, language="ko")
        article.download()
        article.parse()
        return clean_text(article.text)
    except Exception:
        return ""


def fetch_naver_news():
    results = []
    seen_titles = set()
    seen_links = set()

    for keyword in KEYWORDS:
        url = f"https://search.naver.com/search.naver?where=news&query={quote(keyword)}&sort=1"

        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")

            items = soup.select(".news_area")

            for item in items:
                title_tag = item.select_one("a.news_tit")
                info_tags = item.select(".info_group .info")

                if not title_tag:
                    continue

                title = title_tag.get("title", "").strip()
                link = title_tag.get("href", "").strip()

                time_text = "방금 전"
                for info in info_tags:
                    txt = info.get_text(strip=True)
                    if "전" in txt:
                        time_text = parse_naver_time(txt)
                        break

                if not title or not link:
                    continue

                if title in seen_titles or link in seen_links:
                    continue

                seen_titles.add(title)
                seen_links.add(link)

                body = get_article_body(link)

                if len(body) < 120:
                    continue

                summary = summarize_text(body, 100, 200)

                results.append({
                    "keyword": keyword,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published_ago": time_text
                })

                time.sleep(0.3)

                if len(results) >= 20:
                    return results

        except Exception as e:
            print(f"[ERROR] {keyword}: {e}")

    return results


@app.route("/")
def index():
    news_list = fetch_naver_news()
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return render_template(
        "index.html",
        news_list=news_list,
        updated_at=updated_at
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
