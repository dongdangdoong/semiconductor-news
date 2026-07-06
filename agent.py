import requests
from bs4 import BeautifulSoup
from newspaper import Article
from urllib.parse import quote
from datetime import datetime
import re
import time
import json
import os

KEYWORDS = [
    "반도체",
    "삼성전자",
    "SK하이닉스",
    "HBM",
    "DRAM",
    "NAND",
    "AI 반도체",
    "파운드리",
    "TSMC",
    "마이크론"
    "엔비디아"
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


def get_article_body(url):
    try:
        article = Article(url, language="ko")
        article.download()
        article.parse()
        return clean_text(article.text)
    except Exception:
        return ""


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
            res = requests.get(rss_url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.content, "xml")

            items = soup.find_all("item")

            for item in items:
                title = clean_text(item.title.text) if item.title else ""
                link = clean_text(item.link.text) if item.link else ""
                pub_date = clean_text(item.pubDate.text) if item.pubDate else ""

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
                    "published_ago": pub_date
                })

                time.sleep(0.3)

                if len(results) >= 20:
                    return results

        except Exception as e:
            print(f"[ERROR] {keyword}: {e}")

    return results


if __name__ == "__main__":
    news = fetch_news()

    os.makedirs("data", exist_ok=True)

    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(news)} articles to data/news.json")
