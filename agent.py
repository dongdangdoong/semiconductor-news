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

STOCK_KEYWORDS = [
    "주가", "급등", "급락", "상승", "하락", "강세", "약세",
    "신고가", "순매수", "순매도", "특징주", "장중", "마감",
    "코스피", "코스닥", "증시", "시총", "외국인", "기관 매수",
    "목표주가", "투자의견"
]

VIDEO_KEYWORDS = [
    "영상", "동영상", "유튜브", "youtube", "youtu.be",
    "shorts", "watch?v=", "tv.naver", "네이버tv", "채널A",
    "뉴스 영상", "라이브"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}


def clean_html(text):
    text = BeautifulSoup(text or "", "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def clean_space(text):
    return re.sub(r"\s+", " ", text or "").strip()


def clean_article_text(text):
    if not text:
        return ""

    lines = []
    for line in text.splitlines():
        line = clean_space(line)
        if line:
            lines.append(line)

    return "\n".join(lines)


def strip_source_from_title(title):
    title = clean_html(title)

    # Google News RSS 제목의 " - 언론사" 제거
    title = re.sub(r"\s[-–]\s[^-–]{2,40}$", "", title)

    # 불필요한 말머리 제거
    title = re.sub(r"^\[[^\]]+\]\s*", "", title)
    title = re.sub(r"^\([^\)]+\)\s*", "", title)

    return title.strip()


def strip_reporter_and_source(text):
    text = text or ""

    # 기자명 제거
    text = re.sub(r"[가-힣]{2,4}\s?기자", "", text)

    # 메일 주소 제거
    text = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "", text)

    # 맨 앞 지역/언론사 대괄호 제거
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)

    # 문장 끝의 "- 언론사" 형태 제거
    text = re.sub(r"\s[-–]\s[가-힣A-Za-z0-9 .·&]+$", "", text)

    # 흔한 기사 안내문 제거
    text = re.sub(r"무단 전재.*?금지", "", text)
    text = re.sub(r"저작권자.*?금지", "", text)

    return clean_space(text)


def is_video_article(title, url, text):
    check = f"{title} {url} {text[:800]}".lower()
    return any(word.lower() in check for word in VIDEO_KEYWORDS)


def is_stock_news(title, text):
    check = f"{title} {text[:800]}"
    return any(word in check for word in STOCK_KEYWORDS)


def normalize_title(title):
    title = strip_source_from_title(title)
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
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        path = parsed.path.strip("/")

        if path:
            display = f"{domain}/{path}"
        else:
            display = domain

        return display[:58] + "..." if len(display) > 58 else display

    except Exception:
        return url[:58] + "..." if len(url) > 58 else url


def compact_ending(sentence):
    sentence = strip_reporter_and_source(sentence)

    replacements = [
        ("했다고 밝혔다", "발표"),
        ("라고 밝혔다", "언급"),
        ("이라고 밝혔다", "언급"),
        ("밝혔다", "발표"),
        ("전했다", "전언"),
        ("설명했다", "설명"),
        ("강조했다", "강조"),
        ("예정이다", "예정"),
        ("계획이다", "계획"),
        ("전망된다", "전망"),
        ("예상된다", "예상"),
        ("것으로 보인다", "전망"),
        ("것으로 예상된다", "예상"),
        ("것으로 전망된다", "전망"),
        ("진행하고 있다", "진행 중"),
        ("이어지고 있다", "지속"),
        ("나타나고 있다", "확인"),
        ("확대하고 있다", "확대"),
        ("늘리고 있다", "확대"),
        ("줄이고 있다", "축소"),
        ("감소하고 있다", "감소"),
        ("상승하고 있다", "상승"),
        ("하락하고 있다", "하락"),
        ("증가했다", "증가"),
        ("감소했다", "감소"),
        ("확대됐다", "확대"),
        ("축소됐다", "축소"),
        ("했다", "진행"),
        ("했다.", "진행"),
        ("습니다", ""),
        ("입니다", "")
    ]

    for old, new in replacements:
        sentence = sentence.replace(old, new)

    sentence = sentence.rstrip(".")
    return clean_space(sentence)


def make_compact_summary(body, title="", max_len=230):
    body = clean_article_text(body)

    paragraphs = [p for p in body.split("\n") if len(clean_space(p)) >= 30]

    # 핵심: 첫 문단과 두 번째 문단 우선 사용
    source = " ".join(paragraphs[:2]) if paragraphs else body
    source = strip_reporter_and_source(source)

    if not source:
        source = title

    sentences = re.split(r"(?<=[.!?。！？다])\s+", source)
    sentences = [strip_reporter_and_source(s) for s in sentences if len(strip_reporter_and_source(s)) >= 25]

    picked = []

    for s in sentences:
        picked.append(compact_ending(s))
        if len(picked) >= 2:
            break

    if not picked:
        picked = [compact_ending(source[:max_len])]

    summary = " ".join(picked)
    summary = strip_reporter_and_source(summary)

    # 너무 길면 첫 230자에서 정리
    if len(summary) > max_len:
        summary = summary[:max_len].rstrip()

    return summary


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

        body = clean_article_text(article.text)
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
                raw_title = clean_html(item.title.text if item.title else "")
                title = strip_source_from_title(raw_title)

                google_link = clean_html(item.link.text if item.link else "")
                pub_date = clean_html(item.pubDate.text if item.pubDate else "")

                if not title or not google_link:
                    continue

                if is_similar_title(title, seen_titles):
                    continue

                body, real_link = get_article_body(google_link)
                final_link = real_link or google_link

                if final_link in seen_links:
                    continue

                # 영상 기사 제외
                if is_video_article(title, final_link, body):
                    continue

                # 본문 100자 미만 기사 제외
                if len(clean_space(body)) < 100:
                    continue

                # 주가 기사 제외
                if is_stock_news(title, body):
                    continue

                summary = make_compact_summary(body, title)

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

                print(f"Added: {title[:45]}")

                time.sleep(0.25)

        except Exception as e:
            print(f"[ERROR] {keyword}: {e}")

    # 시간순 정렬: 최신 기사 먼저
    results = sorted(results, key=lambda x: x.get("published_ts", 0), reverse=True)

    # 최종 20개
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
