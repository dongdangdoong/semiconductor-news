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
    "삼성전자",
    "SK하이닉스",
    "HBM",
    "DRAM",
    "NAND",
    "D램",
    "메모리",
    "1나노",
    "2나노",
    "3나노",
    "4나노",
    "5나노",
    "6나노",
    "7나노",
    "8나노",
    "9나노",
    "10나노",
    "AI 반도체",
    "AI 칩",
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
    "shorts", "watch?v=", "tv.naver", "네이버tv",
    "뉴스 영상", "라이브", "shorts"
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


def strip_source_from_title(title):
    title = clean_html(title)

    # Google News 제목 뒤의 " - 언론사" 제거
    title = re.sub(r"\s[-–]\s[^-–]{2,50}$", "", title)

    # 말머리 제거
    title = re.sub(r"^\[[^\]]+\]\s*", "", title)
    title = re.sub(r"^\([^\)]+\)\s*", "", title)

    return title.strip()


def strip_reporter_and_source(text):
    text = text or ""

    text = re.sub(r"[가-힣]{2,4}\s?기자", "", text)
    text = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "", text)
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)
    text = re.sub(r"\s[-–]\s[가-힣A-Za-z0-9 .·&]+$", "", text)
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
def is_mostly_english(text):
    text = clean_space(text)
    if not text:
        return False

    korean_count = len(re.findall(r"[가-힣]", text))
    english_count = len(re.findall(r"[A-Za-z]", text))

    return english_count > korean_count * 1.5 and english_count >= 30


def translate_to_korean(text):
    text = clean_space(text)

    if not text:
        return text

    if not is_mostly_english(text):
        return text

    try:
        from deep_translator import GoogleTranslator

        # 너무 긴 본문 전체 번역은 실패 가능성이 높아서 앞부분 중심 번역
        target = text[:1800]
        translated = GoogleTranslator(source="auto", target="ko").translate(target)
        return clean_space(translated)

    except Exception as e:
        print(f"[WARN] translation failed: {e}")
        return text


def remove_question_exclamation(text):
    text = text.replace("?", "")
    text = text.replace("!", "")
    text = text.replace("？", "")
    text = text.replace("！", "")
    return clean_space(text)


def normalize_content_for_dedupe(text):
    text = strip_reporter_and_source(text)
    text = re.sub(r"[^가-힣a-zA-Z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def content_similarity(a, b):
    a = normalize_content_for_dedupe(a)
    b = normalize_content_for_dedupe(b)

    if not a or not b:
        return 0

    # 너무 짧은 텍스트는 제목 유사도에 가까운 비교
    if len(a) < 120 or len(b) < 120:
        return SequenceMatcher(None, a, b).ratio()

    def shingles(text, n=5):
        words = text.split()
        if len(words) < n:
            return set(words)
        return set(tuple(words[i:i+n]) for i in range(len(words) - n + 1))

    a_set = shingles(a)
    b_set = shingles(b)

    if not a_set or not b_set:
        return 0

    return len(a_set & b_set) / len(a_set | b_set)


def dedupe_by_content_keep_two(items, threshold=0.20, max_per_group=2):
    groups = []

    for item in items:
        placed = False

        for group in groups:
            base = group[0]

            title_similar = SequenceMatcher(
                None,
                normalize_title(item["title"]),
                normalize_title(base["title"])
            ).ratio() >= 0.68

            body_similar = content_similarity(
                item.get("dedupe_text", ""),
                base.get("dedupe_text", "")
            ) >= threshold

            if title_similar or body_similar:
                group.append(item)
                placed = True
                break

        if not placed:
            groups.append([item])

    selected = []

    for group in groups:
        # 같은 내용 그룹 안에서는 본문 길이가 긴 기사 우선
        group = sorted(
            group,
            key=lambda x: x.get("body_len", 0),
            reverse=True
        )

        selected.extend(group[:max_per_group])

    return selected

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


def make_compact_summary(text, title="", min_len=100, max_len=200):
    text = strip_reporter_and_source(text)
    text = translate_to_korean(text)

    if not text:
        text = title

    # 첫 문단 혹은 둘째 문단 느낌을 살리기 위해 기사 앞부분 중심 사용
    paragraphs = re.split(r"\n+|(?<=다\.)\s+", text)
    paragraphs = [
        strip_reporter_and_source(p)
        for p in paragraphs
        if len(strip_reporter_and_source(p)) >= 25
    ]

    source = " ".join(paragraphs[:2]) if paragraphs else text
    source = strip_reporter_and_source(source)

    sentences = re.split(r"(?<=[.!?。！？다])\s+", source)
    sentences = [
        strip_reporter_and_source(s)
        for s in sentences
        if len(strip_reporter_and_source(s)) >= 20
    ]

    picked = []

    for s in sentences:
        s = compact_ending(s)
        s = remove_question_exclamation(s)

        if not s:
            continue

        picked.append(s)

        if len(" ".join(picked)) >= min_len or len(picked) >= 2:
            break

    if not picked:
        picked = [compact_ending(source[:max_len])]

    summary = " ".join(picked)
    summary = strip_reporter_and_source(summary)
    summary = remove_question_exclamation(summary)

    # 언론사명처럼 붙는 "- XXX" 제거
    summary = re.sub(r"\s[-–]\s[가-힣A-Za-z0-9 .·&]+$", "", summary)

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

        body = article.text or ""
        body = body.replace("\r", "\n")
        body = re.sub(r"\n{2,}", "\n", body)
        body = strip_reporter_and_source(body)

        return body, real_url

    except Exception:
        return "", url


def fetch_news():
    results = []
    seen_links = set()
    seen_titles = []

    stats = {
        "added": 0,
        "duplicate": 0,
        "video": 0,
        "stock": 0,
        "too_short": 0,
        "body_fallback": 0
    }

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
                title = translate_to_korean(title)
                title = remove_question_exclamation(title)

                google_link = clean_html(item.link.text if item.link else "")
                description = clean_html(item.description.text if item.description else "")
                pub_date = clean_html(item.pubDate.text if item.pubDate else "")

                if not title or not google_link:
                    continue

                body, real_link = get_article_body(google_link)
                final_link = real_link or google_link

                if final_link in seen_links:
                    stats["duplicate"] += 1
                    continue

                # 본문 추출 실패 시 RSS 설명문으로 대체
                if len(clean_space(body)) >= 100:
                    summary_source = body
                else:
                    summary_source = description
                    stats["body_fallback"] += 1

                # 그래도 100자 미만이면 제외
                if len(clean_space(summary_source)) < 100:
                    stats["too_short"] += 1
                    continue

                if is_video_article(title, final_link, summary_source):
                    stats["video"] += 1
                    continue

                if is_stock_news(title, summary_source):
                    stats["stock"] += 1
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
                    "published_ts": published_datetime(pub_date).timestamp(),
                    "body_len": len(clean_space(summary_source)),
                    "dedupe_text": summary_source[:2000]
                })

                stats["added"] += 1
                print(f"Added: {title[:45]}")

                time.sleep(0.15)

        except Exception as e:
            print(f"[ERROR] {keyword}: {e}")

    results = sorted(results, key=lambda x: x.get("published_ts", 0), reverse=True)
    results = results[:20]

    for item in results:
        item.pop("published_ts", None)

    print("Stats:", stats)

    return results


if __name__ == "__main__":
    news = fetch_news()

    os.makedirs("data", exist_ok=True)

    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(news)} articles to data/news.json")
