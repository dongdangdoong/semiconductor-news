import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
import time
import json
import os

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
    text = BeautifulSoup(text or "", "html.parser").get_text(" ")
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


def published_ago(pub_date):
    try:
        published = parsedate_to_datetime(pub_date)
        now = datetime.now(timezone.utc)
        diff = now - published

        minutes = int(diff.total_seconds() // 60)
        hours = int(diff.total_seconds() // 3600)
        days = diff.days

        if minutes < 60:
            return f"{minutes}분 전"
        elif hours < 24:
            return f"{hours}시간 전"
        else:
            return f"{days}일 전"
    except Exception:
        return "시간 정보 없음"


def fetch_news():
    results = []
    seen_titles = set()
    seen_links = set()

    for keyword in KEYWORDS:
        rss_url = (
            "https://news.google.com/rss/search?"
            f"q={quote(keyword)}"
            "&hl=ko&gl=KR&ceid=KR:ko"
        )

        try:
            res = requests.get(rss_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.content, "xml")

            items = soup.find_all("item")
            print(f"[{keyword}] RSS items: {len(items)}")

            for item in items:
                title = clean_text(item.title.text if item.title else "")
                link = clean_text(item.link.text if item.link else "")
                description = clean_text(item.description.text if item.description else "")
                pub_date = clean_text(item.pubDate.text if item.pubDate else "")

                if not title or not link:
                    continue

                if title in seen_titles or link in seen_links:
                    continue

                seen_titles.add(title)
                seen_links.add(link)

                summary_source = description if len(description) >= 50 else title
                summary = summarize_text(summary_source, 60, 200)

                results.append({
                    "keyword": keyword,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published_ago": published_ago(pub_date)
                })

                if len(results) >= 20:
                    return results

                time.sleep(0.1)

        except Exception as e:
            print(f"[ERROR] {keyword}: {e}")

    return results


if __name__ == "__main__":
    news = fetch_news()

    os.makedirs("data", exist_ok=True)

    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(news)} articles to data/news.json")
