import os
import re
import json
import time
import warnings
import requests
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from newspaper import Article
from urllib.parse import quote, urlparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

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
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
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
        sentence = sentence.strip()
        if not sentence:
            continue

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

        if minutes < 1:
            return "방금 전"
        elif minutes < 60:
            return f"{minutes}분 전"
        elif hours < 24:
            return f"{hours}시간 전"
        else:
            return f"{days}일 전"
    except Exception:
        return "시간 정보 없음"


def normalize_title(title):
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"\[[^\]]+\]|\([^\)]+\)", "", title)
    title = re.sub(r"[^가-힣a-zA-Z0-9 ]", "", title)
    return title.strip().lower()


def is_similar_title(title, existing_titles, threshold=0.72):
    title_norm = normalize_title(title)

    for old in existing_titles:
        old_norm = normalize_title(old)
        ratio = SequenceMatcher(None, title_norm, old_norm).ratio()

        if ratio >= threshold:
            return True

    return False


def resolve_url(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=10,
            allow_redirects=True
        )
        return response.url
    except Exception:
        return url


def get_article_body(url):
    try:
        real_url = resolve_url(url)

        article = Article(real_url, language="ko")
        article.download()
        article.parse()

        body = clean_text(article.text)
        return body, real_url

    except Exception:
        return "", url


def fetch_news():
    results = []
    seen_links = set()
    seen_titles = []

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
                google_link = clean_text(item.link.text if item.link else "")
                description = clean_text(item.description.text if item.description else "")
                pub_date = clean_text(item.pubDate.text if item.pubDate else "")

                if not title or not google_link:
                    continue

                if is_similar_title(title, seen_titles):
                    continue

                body, real_link = get_article_body(google_link)

                final_link = real_link or google_link

                if final_link in seen_links:
                    continue

                seen_links.add(final_link)
                seen_titles.append(title)

                if len(body) >= 120:
                    summary = summarize_text(body, 100, 200)
                elif len(description) >= 50:
                    summary = summarize_text(description, 100, 200)
                else:
                    summary = summarize_text(title, 60, 200)

                results.append({
                    "keyword": keyword,
                    "title": title,
                    "link": final_link,
                    "summary": summary,
                    "published_ago": published_ago(pub_date),
                    "published_raw": pub_date
                })

                print(f"Added: {title[:40]}")

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
