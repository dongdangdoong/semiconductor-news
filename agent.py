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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.naver.com/"
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

                if not title or not link:
                    continue

                if title in seen_titles or link in seen_links:
                    continue

                seen_titles.add(title)
                seen_links.add(link)

                published_ago = "방금 전"
                for info in info_tags:
                    txt = info.get_text(strip=True)
                    if "전" in txt:
                        published_ago = txt
                        break

                body = get_article_body(link)

                if len(body) < 120:
                    continue

                summary = summarize_text(body, 100, 200)

                results.append({
                    "keyword": keyword,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published_ago": published_ago
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
