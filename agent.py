import os
import re
import json
import time
import warnings
import requests
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from newspaper import Article
from urllib.parse import quote
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

KEYWORDS = [
    "반도체", "삼성전자 반도체", "SK하이닉스", "HBM",
    "DRAM", "NAND", "AI 반도체", "파운드리",
    "TSMC", "마이크론"
]

STOCK_KEYWORDS = [
    "주가", "급등", "급락", "상승", "하락", "강세", "약세",
    "신고가", "순매수", "순매도", "특징주", "장중", "마감",
    "코스피", "코스닥", "증시", "시총", "외국인"
]

VIDEO_KEYWORDS = [
    "영상", "동영상", "유튜브", "youtube", "youtu.be",
    "shorts", "watch?v=", "tv.naver", "네이버tv"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}


def clean_text(text):
    text = BeautifulSoup(text or "", "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def is_video_article(title, url, text):
    check = f"{title} {url} {text[:500]}".lower()
    return any(word.lower() in check for word in VIDEO_KEYWORDS)


def is_stock_news(title, text):
    check = f"{title} {text[:500]}"
    return any(word in check for word in STOCK_KEYWORDS)


def normalize_title(title):
    title = re.sub(r"\[[^\]]+\]|\([^\)]+\)", "", title)
    title = re.sub(r"[^가-힣a-zA-Z0-9 ]", "", title)
    return re.sub(r"\s+", " ", title).strip().lower()


def is_similar_title(title, existing_titles, threshold=0.68):
    title_norm = normalize_title(title)
    for old in existing_titles:
        old_norm = normalize_title(old)
        if SequenceMatcher(None, title_norm, old_norm).ratio() >= threshold:
            return True
    return False


def published_datetime(pub_date):
    try:
        return parsedate_to_datetime(pub_date)
    except Exception:
        return datetime.now(timezone.utc)


def published_ago(pub_date):
    try:
        published = parsedate_to_datetime(pub_date)
        now = datetime.now(timezone.utc)
        diff = now - published

        minutes = int(diff.total_seconds() // 60)
        hours = int(diff.total_seconds() // 3600)

        if minutes < 1:
            return "방금 전"
        elif minutes < 60:
            return f"{minutes}분 전"
        elif hours < 24:
            return f"{hours}시간 전"
        else:
            return f"{diff.days}일 전"
    except Exception:
        return "시간 정보 없음"


def short_link(url):
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    return url[:55] + "..." if len(url) > 55 else url


def make_compact_summary(text, title="", max_len=230):
    text = clean_text(text)

    paragraphs = re.split(r"\n+|(?<=다\.)\s+", text)
    paragraphs = [clean_text(p) for p in paragraphs if len(clean_text(p)) >= 30]

    source = " ".join(paragraphs[:2]) if paragraphs else text
    source = clean_text(source)

    if not source:
        source = title

    source = re.sub(r"[가-힣]{2,4}\s?기자", "", source)
    source = re.sub(r"^\[[^\]]+\]\s*", "", source)
    source = re.sub(r"-\s?[가-힣A-Za-z0-9 .]+$", "", source)
    source = re.sub(r"\s*-\s*[가-힣A-Za-z0-9 .]+$", "", source)

    sentences = re.split(r"(?<=[.!?。！？다])\s+", source)

    picked = []
    for s in sentences:
        s = clean_text(s)
        if not s:
            continue
        picked.append(s)
        if len(" ".join(picked)) >= 120 or len(picked) >= 2:
            break

    summary = clean_text(" ".join(picked))

    if len(summary) < 80:
        summary = source[:max_len]

    replace_map = {
        "했습니다": "진행",
        "했다": "진행",
        "밝혔다": "발표",
        "전했다": "전언",
        "설명했다": "설명",
        "강조했다": "강조",
        "계획이다": "계획",
        "예정이다": "예정",
        "전망된다": "전망",
        "예상된다": "예상",
        "것으로 보인다": "전망",
        "것으로 예상된다": "예상",
        "것으로 전망된다": "전망"
    }

    for old, new in replace_map.items():
        summary = summary.replace(old, new)

    return summary[:max_len].strip()


def resolve_url(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        return response.url
    except Exception:
        return url


def get_article_body(url):
    try:
        real_url = resolve_url(url)
        article = Article(real_url, language="ko")
        article.download()
        article.parse()
        return clean_text(article.text), real_url
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
                summary_source = body if len(body) >= 100 else description

                if final_link in seen_links:
                    continue

                if is_video_article(title, final_link, summary_source):
                    continue

                if is_stock_news(title, summary_source):
                    continue

                if len(summary_source) < 100:
                    continue

                summary = make_compact_summary(summary_source, title)

                seen_links.add(final_link)
                seen_titles.append(title)

                results.append({
                    "title": title,
                    "link": final_link,
                    "short_link": short_link(final_link),
                    "summary": summary,
                    "published_ago": published_ago(pub_date),
                    "published_raw": pub_date,
                    "published_ts": published_datetime(pub_date).timestamp()
                })

                time.sleep(0.25)

        except Exception as e:
            print(f"[ERROR] {keyword}: {e}")

    results = sorted(results, key=lambda x: x.get("published_ts", 0), reverse=True)
    results = results[:20]

    for item in results:
        item.pop("published_ts", None)

    return results


if __name__ == "__main__":
    news = fetch_news()

    os.makedirs("data", exist_ok=True)

    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(news)} articles to data/news.json")
