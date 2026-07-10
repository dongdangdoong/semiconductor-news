import os
import re
import json
import time
import warnings
import requests
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from newspaper import Article
from urllib.parse import quote, urlparse, urljoin
from datetime import datetime, timezone, timedelta
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
    "마이크론",
    # Reuters는 직접 크롤링이 막혀있어 Google 뉴스 site: 검색으로 우회
    "site:reuters.com semiconductor",
    "site:reuters.com chip"
]

# DigiTimes는 사이트 자체가 크롤링을 막고 있지만 공식 RSS는 열려있어 이걸로 수집
ENGLISH_RSS_SOURCES = [
    {"name": "DigiTimes", "url": "https://www.digitimes.com/rss/daily.xml"}
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
    "뉴스 영상", "라이브"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}

SUMMARY_PRIORITY_KEYWORDS = [
    "삼성전자", "SK하이닉스", "TSMC", "마이크론", "엔비디아", "브로드컴",
    "HBM", "DRAM", "D램", "NAND", "낸드", "DDR", "LPDDR",
    "파운드리", "메모리", "AI", "ASIC", "GPU", "서버",
    "수요", "공급", "가격", "투자", "증설", "양산", "공정",
    "2나노", "3나노", "1나노", "EUV", "패키징", "실적"
]

SUMMARY_STOPWORDS = {
    "그리고", "하지만", "그러나", "또한", "이번", "관련", "통해", "대해",
    "위해", "있는", "없는", "지난", "최근", "이날", "올해", "내년",
    "기자", "뉴스", "사진", "제공", "밝혔다", "전했다", "설명했다"
}

SEMICON_KEYWORDS = [
    "반도체", "삼성전자", "SK하이닉스", "HBM", "DRAM", "D램",
    "NAND", "낸드", "메모리", "파운드리", "TSMC", "마이크론",
    "AI 반도체", "AI칩", "AI 칩", "칩", "웨이퍼", "EUV", "패키징",
    "2나노", "3나노", "1나노", "팹", "공정", "양산", "DDR", "LPDDR",
    "낸드플래시", "서버", "GPU", "ASIC", "SSD", "기업용 SSD"
]

HARD_SEMICON_KEYWORDS = [
    "반도체", "HBM", "DRAM", "D램", "NAND", "낸드", "메모리",
    "파운드리", "TSMC", "마이크론", "웨이퍼", "EUV", "패키징",
    "나노", "공정", "팹", "양산", "AI 반도체", "AI칩", "AI 칩",
    "NPU", "GPU", "ASIC", "DDR", "LPDDR", "SSD", "기업용 SSD",
    "낸드플래시", "HBM4", "HBM3E", "CXL", "AP", "엑시노스",
    # 영문 소스(DigiTimes, Reuters 등) 제목 매칭용
    "semiconductor", "semiconductors", "chipmaker", "chipmakers",
    "foundry", "foundries", "wafer", "fab"
]
NON_SEMICON_INDUSTRY_KEYWORDS = [
    "배터리", "이차전지", "2차전지", "ESS", "LFP", "양극재", "음극재",
    "LG엔솔", "LG에너지솔루션", "전기차", "완성차", "GM", "테슬라",
    "로봇", "로보틱스", "나우로보틱스", "스마트팩토리",
    "화장품", "뷰티", "K-뷰티", "AHC", "APR",
    "스피커", "블루투스", "JBL", "하만",
    "바이오", "제약", "헬스케어",
    "축구", "야구", "월드컵", "감독", "선수"
]
COMPANY_KEYWORDS = [
    "삼성전자", "SK하이닉스", "엔비디아", "브로드컴", "TSMC", "마이크론"
]

DIRECT_SOURCE_URLS = [
    {
        "name": "네이버 IT/과학",
        "urls": [
            "https://news.naver.com/section/105"
        ]
    },
    {
        "name": "한국경제",
        "urls": [
            "https://www.hankyung.com/industry/semicon",
            "https://www.hankyung.com/industry/semicon-electronics"
        ]
    },
    {
        "name": "뉴스1",
        "urls": [
            "https://www.news1.kr/it-science/mobile",
            "https://www.news1.kr/it-science/general-it",
            "https://www.news1.kr/industry/electronics"
        ]
    },
    {
        "name": "매일경제",
        "urls": [
            "https://www.mk.co.kr/news/business/semiconductors-electronics"
        ]
    },
    {
        "name": "머니투데이",
        "urls": [
            "https://www.mt.co.kr/industry?page=1"
        ]
    },
    {
        "name": "아시아경제",
        "urls": [
            "https://www.asiae.co.kr/list/enterprise-CEO",
            "https://www.asiae.co.kr/list/IT"
        ]
    },
    {
        "name": "조선비즈",
        "urls": [
            "https://biz.chosun.com/it-science/ict/"
        ]
    },
    {
        "name": "연합뉴스",
        "urls": [
            "https://www.yna.co.kr/industry/electronics?site=footer_industry_depth02",
            "https://www.yna.co.kr/industry/technology-science"
        ]
    },
    {
        "name": "디지털타임스",
        "urls": [
            "https://www.dt.co.kr/industry/general"
        ]
    },
    {
        "name": "디지털데일리",
        "urls": [
            "https://www.ddaily.co.kr/semiconductor"
        ]
    },
    {
        "name": "한겨레",
        "urls": [
            "https://www.hani.co.kr/arti/economy/it"
        ]
    },
    {
        "name": "지디넷코리아",
        "urls": [
            "https://zdnet.co.kr/newskey/?lstcode=%EB%B0%98%EB%8F%84%EC%B2%B4"
        ]
    },
    {
        "name": "전자신문",
        "urls": [
            "https://www.etnews.com/news/section.html?id1=10"
        ]
    },
    {
        "name": "뉴시스",
        "urls": [
            "https://www.newsis.com/business/list/?cid=13000&scid=10414"
        ]
    },
    {
        "name": "이데일리",
        "urls": [
            "https://www.edaily.co.kr/articles/business/electronics"
        ]
    }
]

SOURCE_NOISE_WORDS = [
    "한국경제", "한경", "뉴스1", "매일경제", "머니투데이", "아시아경제",
    "조선비즈", "연합뉴스", "디지털타임스", "디지털데일리", "한겨레",
    "지디넷코리아", "ZDNet Korea", "전자신문", "뉴시스", "이데일리",
    "구글뉴스", "Google 뉴스", "Google News", "네이버뉴스", "네이버 뉴스",
    "Reuters", "Bloomberg", "CNBC", "Financial Times", "Nikkei Asia",
    "DigiTimes", "디지타임스", "디지타임즈"
]

KST = timezone(timedelta(hours=9))

SUMMARY_CACHE = {}

def clean_html(text):
    text = BeautifulSoup(text or "", "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def clean_space(text):
    return re.sub(r"\s+", " ", text or "").strip()


def strip_source_from_title(title):
    title = clean_html(title)

    title = re.sub(r"\s[-–]\s[^-–]{2,50}$", "", title)
    title = re.sub(r"^\[[^\]]+\]\s*", "", title)
    title = re.sub(r"^\([^\)]+\)\s*", "", title)

    return title.strip()


def strip_reporter_and_source(text):
    text = text or ""

    text = re.sub(r"[가-힣]{2,4}\s?기자", " ", text)
    text = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", " ", text)
    text = re.sub(r"^\[[^\]]+\]\s*", " ", text)

    for source in SOURCE_NOISE_WORDS:
        text = text.replace(source, " ")

    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\b[a-zA-Z0-9.-]+\.(com|net|co\.kr|kr|org|news)\b", " ", text)
    text = re.sub(r"\s[-–]\s[가-힣A-Za-z0-9 .·&]+$", " ", text)
    text = re.sub(r"무단 전재.*?금지", " ", text)
    text = re.sub(r"저작권자.*?금지", " ", text)
    text = re.sub(r"재판매 및 DB 금지", " ", text)

    return clean_space(text)


def is_video_article(title, url, text):
    check = f"{title} {url} {text[:800]}".lower()
    return any(word.lower() in check for word in VIDEO_KEYWORDS)


def is_stock_news(title, text):
    check = f"{title} {text[:800]}"
    return any(word in check for word in STOCK_KEYWORDS)

def is_bad_extracted_title(title):
    title = clean_space(title)

    if not title:
        return True

    bad_titles = [
        "Google 뉴스",
        "Google News",
        "뉴스",
        "IT세상을 바꾸는 힘 지디넷코리아",
        "지디넷코리아",
        "ZDNet Korea",
        "한겨레",
        "이데일리",
        "매일경제",
        "한국경제"
    ]

    if title in bad_titles:
        return True

    if len(title) < 8:
        return True

    # 사이트명/슬로건처럼 보이는 제목 제거
    if len(title) <= 20 and any(word in title for word in ["뉴스", "코리아", "신문", "일보"]):
        return True

    return False
    
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


def ensure_utc(dt):
    if dt is None:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def parse_datetime_safe(value):
    if value is None:
        return None

    if isinstance(value, datetime):
        return ensure_utc(value)

    value = clean_space(str(value))
    if not value:
        return None

    try:
        return ensure_utc(parsedate_to_datetime(value))
    except Exception:
        pass

    try:
        return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except Exception:
        return None


def published_datetime(pub_date):
    dt = parse_datetime_safe(pub_date)
    return dt or datetime.now(timezone.utc)


def published_ago_from_datetime(published):
    published = ensure_utc(published)

    if published is None:
        return "시간 정보 없음"

    now = datetime.now(timezone.utc)
    seconds = int((now - published).total_seconds())

    if seconds < 0:
        seconds = 0

    minutes = seconds // 60
    hours = seconds // 3600

    if minutes < 1:
        return "방금 전"
    elif minutes < 60:
        return f"{minutes}분 전"
    elif hours < 24:
        return f"{hours}시간 전"
    else:
        return f"{seconds // 86400}일 전"


def published_ago(pub_date):
    return published_ago_from_datetime(parse_datetime_safe(pub_date))


def is_within_recent_hours(pub_date, hours=24):
    dt = parse_datetime_safe(pub_date)

    if dt is None:
        return False

    now = datetime.now(timezone.utc)
    diff_seconds = (now - dt).total_seconds()

    return 0 <= diff_seconds <= hours * 3600


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


def remove_title_overlap(text, title):
    text = text or ""
    title = strip_source_from_title(title or "")

    if not title:
        return clean_space(text)

    candidates = [
        title,
        title.replace("…", ""),
        title.replace("...", ""),
        re.sub(r"[^가-힣A-Za-z0-9 ]", " ", title)
    ]

    for candidate in candidates:
        candidate = clean_space(candidate)
        if candidate:
            text = text.replace(candidate, " ")

    return clean_space(text)


def sentence_is_too_similar_to_title(sentence, title, threshold=0.52):
    if not title:
        return False

    s = normalize_content_for_dedupe(sentence)
    t = normalize_content_for_dedupe(title)

    if not s or not t:
        return False

    return SequenceMatcher(None, s, t).ratio() >= threshold


def content_similarity(a, b):
    a = normalize_content_for_dedupe(a)
    b = normalize_content_for_dedupe(b)

    if not a or not b:
        return 0

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
        ("했다고 밝혔다", " 발표"),
        ("라고 밝혔다", " 언급"),
        ("이라고 밝혔다", " 언급"),
        ("밝혔다", " 발표"),
        ("라고 말했다", " 언급"),
        ("고 말했다", " 언급"),
        ("전했다", " 전언"),
        ("라고 전했다", " 전언"),
        ("설명했다", " 설명"),
        ("라고 설명했다", " 설명"),
        ("강조했다", " 강조"),
        ("라고 강조했다", " 강조"),
        ("덧붙였다", " 덧붙임"),
        ("것으로 알려졌다", " 확인"),
        ("알려졌다", " 확인"),
        ("것으로 나타났다", " 확인"),
        ("나타났다", " 확인"),
        ("것으로 파악됐다", " 파악"),
        ("파악됐다", " 파악"),
        ("것으로 드러났다", " 확인"),
        ("드러났다", " 확인"),
        ("것으로 조사됐다", " 조사"),
        ("조사됐다", " 조사"),
        ("것으로 집계됐다", " 집계"),
        ("집계됐다", " 집계"),
        ("것으로 관측된다", " 관측"),
        ("관측된다", " 관측"),
        ("것으로 분석된다", " 분석"),
        ("분석된다", " 분석"),
        ("예정이다", " 예정"),
        ("계획이다", " 계획"),
        ("방침이다", " 방침"),
        ("전망된다", " 전망"),
        ("예상된다", " 예상"),
        ("것으로 보인다", " 전망"),
        ("것으로 예상된다", " 예상"),
        ("것으로 전망된다", " 전망"),
        ("진행하고 있다", " 진행 중"),
        ("이어지고 있다", " 지속"),
        ("나타나고 있다", " 확인"),
        ("확대하고 있다", " 확대"),
        ("늘리고 있다", " 확대"),
        ("줄이고 있다", " 축소"),
        ("감소하고 있다", " 감소"),
        ("상승하고 있다", " 상승"),
        ("하락하고 있다", " 하락"),
        ("증가했다", " 증가"),
        ("감소했다", " 감소"),
        ("확대됐다", " 확대"),
        ("축소됐다", " 축소"),
        ("출시했다", " 출시"),
        ("공개했다", " 공개"),
        ("선보였다", " 공개"),
        ("투자했다", " 투자"),
        ("인수했다", " 인수"),
        ("체결했다", " 체결"),
        ("합의했다", " 합의"),
        ("결정했다", " 결정"),
        ("발표했다", " 발표"),
        ("추진한다", " 추진"),
        ("검토한다", " 검토"),
        ("논의한다", " 논의"),
        ("협력한다", " 협력"),
        ("습니다", ""),
        ("입니다", "")
    ]

    for old, new in replacements:
        sentence = sentence.replace(old, new)

    sentence = sentence.rstrip(".")
    sentence = clean_space(sentence)

    # 위 표에서 못 잡은 문장은 문장 끝 종결어미만 잘라내서
    # 단어(명사)로 끝나는 개조식 문장으로 정리한다 (문장 중간은 건드리지 않음)
    generic_endings = [
        "하고 있다", "되고 있다", "해야 한다", "할 예정이다",
        "했다", "한다", "됐다", "된다", "였다", "이었다", "이다",
        "있다", "없다", "왔다", "낸다", "온다", "든다",
        "늘렸다", "줄였다", "커졌다", "작아졌다", "높였다", "낮췄다"
    ]
    for ending in sorted(generic_endings, key=len, reverse=True):
        if sentence.endswith(ending):
            sentence = sentence[: -len(ending)].rstrip()
            break

    sentence = sentence.rstrip(",.·- ")
    return clean_space(sentence)


def split_sentences_for_summary(text):
    text = strip_reporter_and_source(text)
    text = re.sub(r"\s+", " ", text).strip()

    sentences = re.split(r"(?<=[.!?。！？다])\s+", text)

    cleaned = []
    for s in sentences:
        s = strip_reporter_and_source(s)
        s = remove_question_exclamation(s)

        if len(s) < 25:
            continue

        if len(s) > 180:
            s = s[:180].rstrip()

        cleaned.append(s)

    return cleaned


def extract_summary_keywords(text, top_n=12):
    text = strip_reporter_and_source(text)

    words = re.findall(r"[가-힣A-Za-z0-9]+", text)
    counter = {}

    for word in words:
        word = word.strip()

        if len(word) < 2:
            continue

        if word in SUMMARY_STOPWORDS:
            continue

        counter[word] = counter.get(word, 0) + 1

    ranked = sorted(counter.items(), key=lambda x: x[1], reverse=True)

    return [word for word, _ in ranked[:top_n]]


def score_summary_sentence(sentence, keywords, index):
    score = 0
    lower_sentence = sentence.lower()

    for keyword in keywords:
        if keyword.lower() in lower_sentence:
            score += 2

    for keyword in SUMMARY_PRIORITY_KEYWORDS:
        if keyword.lower() in lower_sentence:
            score += 3

    if re.search(r"\d", sentence):
        score += 2

    if any(unit in sentence for unit in ["조", "억", "%", "달러", "원", "년", "분기", "월", "나노"]):
        score += 2

    if 45 <= len(sentence) <= 150:
        score += 2
    elif len(sentence) < 35:
        score -= 1
    elif len(sentence) > 170:
        score -= 1

    score += max(0, 2 - index * 0.08)

    return score


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

SUMMARY_CACHE_PATH = os.path.join("data", "summary_cache.json")
SUMMARY_CACHE_MAX_AGE_HOURS = 72  # 이 시간이 지난 캐시 항목은 다음 실행 때 정리됨


def load_summary_cache():
    try:
        with open(SUMMARY_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def prune_summary_cache(cache):
    now_ts = datetime.now(timezone.utc).timestamp()
    pruned = {}

    for link, entry in cache.items():
        cached_at = entry.get("cached_at", 0)
        if now_ts - cached_at <= SUMMARY_CACHE_MAX_AGE_HOURS * 3600:
            pruned[link] = entry

    return pruned


def save_summary_cache(cache):
    try:
        os.makedirs("data", exist_ok=True)
        with open(SUMMARY_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] summary cache 저장 실패: {e}")


def extract_numbers(text):
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


def summarize_with_gemini(literal_title, body):
    if not GEMINI_API_KEY:
        return None, None

    prompt = (
        "다음은 반도체 관련 뉴스 기사입니다. 한국 경제지 뉴스 헤드라인 및 기사 요약 스타일로 "
        "'제목'과 '요약' 두 가지를 작성해주세요.\n\n"
        "['제목' 작성 규칙 — 매우 중요]\n"
        "- 아래 '원문 제목(직역)'에 담긴 사실관계만 사용해서 자연스러운 한국어 헤드라인으로 다듬을 것\n"
        "- 본문에 있더라도 원문 제목에 없는 새로운 사실·수치·기업명을 제목에 추가하지 말 것 "
        "(제목은 번역/윤문만 하고, 본문 내용을 가져와 새로 작성하지 말 것)\n"
        "- 원문 제목에 숫자가 있으면 반드시 그 숫자를 그대로 유지할 것\n"
        "- 실제 한국 경제 뉴스 헤드라인처럼 짧고 간결하게 작성 (예: 25~40자)\n"
        "- 조사(은/는/이/가/을/를)는 꼭 필요한 경우가 아니면 생략\n"
        "- 서술형 종결어미('~다', '~했다') 대신 명사(단어)로 끝맺을 것\n"
        "- 번역투가 아니라 한국 기자가 직접 쓴 것처럼 자연스럽게 작성\n\n"
        "['요약' 작성 규칙]\n"
        "- 100~200자 내외, 본문 전체를 참고해서 작성\n"
        "- 개조식 문체로 작성. 문장을 '~다', '~했음', '~습니다' 같은 서술형 종결어미가 아니라 "
        "'~확대', '~발표', '~전망'처럼 명사(단어)로 끝맺을 것\n"
        "- 기사에 나온 핵심 사실(수치, 기업명, 제품명 등)을 최대한 구체적으로 포함\n"
        "- 기사에 없는 내용을 추측하거나 과장하지 말 것\n"
        "- 번역투가 아니라 한국 기자가 직접 쓴 기사처럼 자연스럽게 작성\n\n"
        "[예시]\n"
        "원문 제목(직역): 삼성전자, 3나노 파운드리에서 새로운 고객사를 확보하다\n"
        "제목: 삼성전자, 3나노 파운드리 신규 고객사 확보\n"
        "요약: 삼성전자가 3나노 공정 파운드리 사업에서 신규 고객사를 확보했다고 발표. "
        "이번 계약으로 시스템반도체 부문 매출 확대 전망. TSMC와의 파운드리 경쟁 심화 예상.\n\n"
        "[출력 형식 — 아래 두 줄만 정확히 이 형식으로 출력, 다른 말이나 마크다운 기호 금지]\n"
        "제목: <헤드라인>\n"
        "요약: <요약문>\n\n"
        f"원문 제목(직역): {literal_title}\n\n"
        f"본문(요약 작성에만 참고):\n{body[:3500]}"
    )

    try:
        res = requests.post(
            GEMINI_ENDPOINT,
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400}
            },
            timeout=20
        )

        if res.status_code != 200:
            print(f"[Gemini] HTTP {res.status_code}: {res.text[:200]}")
            return None, None

        data = res.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None, None

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None, None

        raw_text = parts[0].get("text", "")

        title_match = re.search(r"제목\s*[:：]\s*(.+)", raw_text)
        summary_match = re.search(r"요약\s*[:：]\s*(.+(?:\n.+)*)", raw_text)

        new_title = clean_space(title_match.group(1)) if title_match else ""
        new_title = new_title.strip("\"'“”‘’ \n")

        summary = clean_space(summary_match.group(1)) if summary_match else ""
        summary = summary.strip("\"'“”‘’ \n")

        if not summary or len(summary) < 20:
            return None, None

        if len(summary) > 220:
            summary = summary[:220].rstrip()

        if new_title and len(new_title) > 60:
            new_title = new_title[:60].rstrip()

        # 안전장치: 원문 제목에 있던 숫자(수치)가 새 제목에서 빠지거나 바뀌었으면
        # 사실관계 왜곡 가능성이 있다고 보고 새 제목을 버리고 직역 제목을 그대로 사용
        if new_title:
            original_numbers = extract_numbers(literal_title)
            new_numbers = extract_numbers(new_title)
            if original_numbers and not original_numbers.issubset(new_numbers):
                print(f"[Gemini] 제목 숫자 불일치로 직역 제목 유지: '{literal_title}' → '{new_title}' 거부")
                new_title = None

        return (new_title or None), summary

    except Exception as e:
        print(f"[Gemini ERROR] {e}")
        return None, None


def summarize_article(link, title, body_text, translate_title=False):
    """캐시 → Gemini → 규칙기반 순으로 (제목, 요약)을 생성한다.
    30분마다 도는 크론 특성상 같은 기사를 반복 요약하지 않도록 링크 기준 캐시를 우선 사용한다.
    translate_title=True면 해외 기사 원제목 대신 Gemini가 새로 쓴 한국어 헤드라인을 사용한다."""
    cached = SUMMARY_CACHE.get(link)
    if cached and cached.get("summary"):
        final_title = cached.get("title") if (translate_title and cached.get("title")) else title
        return final_title, cached["summary"]

    gemini_title, summary = summarize_with_gemini(title, body_text)
    source = "gemini" if summary else None

    if not summary:
        summary = make_compact_summary(body_text, title=title)
        source = "rule_based"

    final_title = gemini_title if (translate_title and gemini_title) else title

    SUMMARY_CACHE[link] = {
        "title": gemini_title or "",
        "summary": summary,
        "source": source,
        "cached_at": datetime.now(timezone.utc).timestamp()
    }

    return final_title, summary


def make_compact_summary(text, title="", min_len=100, max_len=200):
    # 제목은 요약 재료로 사용하지 않고, 제목과 비슷한 문장 제거용으로만 사용
    text = strip_reporter_and_source(text)
    text = remove_title_overlap(text, title)
    text = translate_to_korean(text)

    if not text:
        return ""

    sentences = split_sentences_for_summary(text)

    cleaned_sentences = []
    for s in sentences:
        s = strip_reporter_and_source(s)
        s = remove_title_overlap(s, title)
        s = remove_question_exclamation(s)

        if len(s) < 25:
            continue

        if sentence_is_too_similar_to_title(s, title):
            continue

        cleaned_sentences.append(s)

    if not cleaned_sentences:
        fallback = strip_reporter_and_source(text[:max_len])
        fallback = remove_title_overlap(fallback, title)
        fallback = compact_ending(fallback)
        fallback = remove_question_exclamation(fallback)
        return fallback[:max_len].rstrip()

    keywords = extract_summary_keywords(text)

    ranked = []
    for idx, sentence in enumerate(cleaned_sentences[:40]):
        ranked.append((idx, sentence, score_summary_sentence(sentence, keywords, idx)))

    ranked = sorted(ranked, key=lambda x: x[2], reverse=True)

    picked = []

    for idx, sentence, _ in ranked:
        sentence = compact_ending(sentence)
        sentence = strip_reporter_and_source(sentence)
        sentence = remove_title_overlap(sentence, title)
        sentence = remove_question_exclamation(sentence)

        if not sentence:
            continue

        duplicate = False
        for _, old_sentence in picked:
            if SequenceMatcher(
                None,
                normalize_content_for_dedupe(sentence),
                normalize_content_for_dedupe(old_sentence)
            ).ratio() >= 0.72:
                duplicate = True
                break

        if duplicate:
            continue

        picked.append((idx, sentence))

        joined = " ".join([s for _, s in sorted(picked, key=lambda x: x[0])])
        if len(joined) >= min_len or len(picked) >= 2:
            break

    picked = sorted(picked, key=lambda x: x[0])
    summary = " ".join([s for _, s in picked])

    if not summary:
        summary = compact_ending(text[:max_len])

    summary = strip_reporter_and_source(summary)
    summary = remove_title_overlap(summary, title)
    summary = remove_question_exclamation(summary)
    summary = re.sub(r"\s[-–]\s[가-힣A-Za-z0-9 .·&]+$", "", summary)
    summary = clean_space(summary)

    if len(summary) > max_len:
        summary = summary[:max_len].rstrip()

    return summary


def clean_direct_title(source_name, anchor_tag):
    title_candidates = []

    title_attr = clean_space(anchor_tag.get("title", ""))
    if title_attr:
        title_candidates.append(title_attr)

    aria_label = clean_space(anchor_tag.get("aria-label", ""))
    if aria_label:
        title_candidates.append(aria_label)

    img = anchor_tag.select_one("img")
    if img:
        alt = clean_space(img.get("alt", ""))
        if alt:
            title_candidates.append(alt)

    for selector in [
        "h1", "h2", "h3", "h4",
        "strong", "b",
        ".title", ".tit", ".headline", ".subject", ".news_tit", ".txt"
    ]:
        node = anchor_tag.select_one(selector)
        if node:
            txt = clean_space(node.get_text(" "))
            if txt:
                title_candidates.append(txt)

    strings = [clean_space(s) for s in anchor_tag.stripped_strings]
    strings = [s for s in strings if len(s) >= 8]

    if strings:
        # 지디넷·이데일리·한겨레 등에서 a 태그 안에 제목+요약이 같이 들어오는 경우가 있어
        # 가장 제목처럼 보이는 짧은 문자열을 우선 사용
        strings_sorted = sorted(strings, key=lambda x: (len(x) > 90, len(x)))
        title_candidates.extend(strings_sorted)

    raw_text = clean_space(anchor_tag.get_text(" "))
    if raw_text:
        title_candidates.append(raw_text)

    cleaned_candidates = []

    for candidate in title_candidates:
        candidate = strip_source_from_title(candidate)
        candidate = remove_question_exclamation(candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip()

        # 제목 뒤에 본문 첫 문장이 붙는 경우를 완화
        # 너무 긴 경우 첫 문장/첫 절 중심으로 자름
        if len(candidate) > 95:
            split_parts = re.split(r"(?<=다)\s+|(?<=요)\s+|(?<=음)\s+|(?<=다\.)\s+|[｜|]", candidate)
            split_parts = [clean_space(p) for p in split_parts if len(clean_space(p)) >= 8]
            if split_parts:
                candidate = split_parts[0]

        # 너무 짧거나 메뉴성 문구 제거
        if len(candidate) < 8:
            continue

        bad_title_words = [
            "로그인", "회원가입", "구독", "검색", "메뉴", "전체기사",
            "많이 본 뉴스", "관련기사", "공유", "댓글", "이전", "다음"
        ]

        if any(bad in candidate for bad in bad_title_words):
            continue

        cleaned_candidates.append(candidate)

    if not cleaned_candidates:
        return ""

    # 너무 긴 후보보다 헤드라인 길이에 가까운 후보 우선
    cleaned_candidates = sorted(
        cleaned_candidates,
        key=lambda x: (
            len(x) > 90,
            len(x) < 12,
            abs(len(x) - 42)
        )
    )

    return cleaned_candidates[0]


def normalize_article_title(title, fallback_title=""):
    title = title or fallback_title or ""
    title = strip_source_from_title(title)
    title = translate_to_korean(title)
    title = remove_question_exclamation(title)
    title = clean_space(title)

    if len(title) > 95:
        split_parts = re.split(r"(?<=다)\s+|(?<=요)\s+|(?<=음)\s+|[｜|]", title)
        split_parts = [clean_space(p) for p in split_parts if len(clean_space(p)) >= 8]
        if split_parts:
            title = split_parts[0]

    return title


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

        # newspaper 자체 다운로더는 일부 사이트(DigiTimes 등)에서 차단/빈 응답이 옴
        # 목록 페이지 크롤링에 이미 성공한 HEADERS로 직접 받아서 넘겨준다
        res = requests.get(real_url, headers=HEADERS, timeout=12)
        res.encoding = res.apparent_encoding or res.encoding
        html = res.text

        # 네이버 뉴스는 newspaper의 일반 추출 알고리즘이 본문 대신
        # "AI 요약봇" 안내 박스(모든 기사에서 길이가 똑같음)를 잘못 집어내는 경우가 있어
        # 실제 본문 컨테이너(#dic_area / #newsct_article)를 직접 지정해서 추출한다
        if "naver.com" in urlparse(real_url).netloc:
            soup = BeautifulSoup(html, "html.parser")
            content_div = soup.select_one("#dic_area") or soup.select_one("#newsct_article")

            if content_div:
                for junk in content_div.select("script, style, .end_photo_org, .ab_sub_bx, .media_end_summary"):
                    junk.decompose()

                body = clean_space(content_div.get_text(" "))
                body = strip_reporter_and_source(body)

                title_meta = soup.find("meta", attrs={"property": "og:title"})
                raw_title = title_meta.get("content") if title_meta else ""
                article_title = normalize_article_title(raw_title or "")

                return body, real_url, article_title

        article = Article(real_url, language="ko")
        article.set_html(html)
        article.parse()

        body = article.text or ""
        body = body.replace("\r", "\n")
        body = re.sub(r"\n{2,}", "\n", body)
        body = strip_reporter_and_source(body)

        article_title = normalize_article_title(article.title or "")

        return body, real_url, article_title

    except Exception:
        return "", url, ""




def get_article_published_datetime(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        res.encoding = res.apparent_encoding or res.encoding
        soup = BeautifulSoup(res.text, "html.parser")

        meta_selectors = [
            ("property", "article:published_time"),
            ("property", "og:article:published_time"),
            ("name", "article:published_time"),
            ("name", "pubdate"),
            ("name", "publishdate"),
            ("name", "date"),
            ("itemprop", "datePublished"),
        ]

        for attr, value in meta_selectors:
            tag = soup.find("meta", attrs={attr: value})
            if tag:
                dt = parse_datetime_safe(tag.get("content", ""))
                if dt:
                    return dt

        time_tag = soup.find("time")
        if time_tag:
            dt = parse_datetime_safe(time_tag.get("datetime") or time_tag.get_text(" "))
            if dt:
                return dt

        # 네이버 등 일부 사이트는 <time> 대신 data-date-time 속성을 사용
        # 이 값은 타임존 정보가 없는 한국시간(KST)이므로 명시적으로 KST로 해석해야 함
        datetime_attr_tag = soup.find(attrs={"data-date-time": True})
        if datetime_attr_tag:
            raw = datetime_attr_tag.get("data-date-time", "")
            m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?", raw)
            if m:
                y, mo, d, hh, mi, se = m.groups()
                se = int(se) if se else 0
                return datetime(int(y), int(mo), int(d), int(hh), int(mi), se, tzinfo=KST).astimezone(timezone.utc)

        text = soup.get_text(" ")
        patterns = [
            r"(?:입력|등록|최초입력|승인|게재)\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\s+(\d{1,2}):(\d{2})",
            r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\s+(\d{1,2}):(\d{2})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                y, m, d, hh, mm = map(int, match.groups())
                return datetime(y, m, d, hh, mm, tzinfo=KST).astimezone(timezone.utc)

        # 오전/오후 형식 (네이버 등): "입력 2026.07.09. 오전 10:23"
        ampm_pattern = r"(?:입력|등록|최초입력|승인|게재)?\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\.?\s*(오전|오후)\s*(\d{1,2}):(\d{2})"
        match = re.search(ampm_pattern, text)
        if match:
            y, m, d, ampm, hh, mm = match.groups()
            y, m, d, hh, mm = int(y), int(m), int(d), int(hh), int(mm)
            if ampm == "오후" and hh != 12:
                hh += 12
            if ampm == "오전" and hh == 12:
                hh = 0
            return datetime(y, m, d, hh, mm, tzinfo=KST).astimezone(timezone.utc)

        return None

    except Exception:
        return None

def looks_like_article_url(url):
    if not url:
        return False

    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()
    full = f"{path}?{query}"

    bad_patterns = [
        "login", "member", "subscribe", "newsletter", "event",
        "advertise", "company", "privacy", "terms", "search",
        "photo", "video", "tv", "youtube", "recruit", "rss",
        "facebook", "twitter", "instagram"
    ]

    if any(bad in full for bad in bad_patterns):
        return False

    good_patterns = [
        "news", "article", "view", "read", "mnews",
        "biz", "it", "industry", "semiconductor",
        "electronics", "arti", "business"
    ]

    if any(good in full for good in good_patterns):
        return True

    if re.search(r"\d{5,}", url):
        return True

    return False


def is_semicon_related(title, url="", text=""):
    title_text = clean_space(title)
    body_text = clean_space(text[:1200])

    check_title = title_text.lower()
    check_body = body_text.lower()
    check_all = f"{title_text} {body_text}".lower()

    hard_hits_title = [
        keyword for keyword in HARD_SEMICON_KEYWORDS
        if keyword.lower() in check_title
    ]

    hard_hits_body = [
        keyword for keyword in HARD_SEMICON_KEYWORDS
        if keyword.lower() in check_body
    ]

    non_semicon_hits = [
        keyword for keyword in NON_SEMICON_INDUSTRY_KEYWORDS
        if keyword.lower() in check_all
    ]

    # 1) 제목에 강한 반도체 키워드가 있으면 통과
    if hard_hits_title:
        return True

    # 2) 타 산업 키워드가 있고, 본문 반도체 키워드가 약하면 제외
    if non_semicon_hits and len(set(hard_hits_body)) < 2:
        return False

    # 3) 본문 앞부분에 강한 반도체 키워드가 2개 이상 있으면 통과
    if len(set(hard_hits_body)) >= 2:
        return True

    # 4) 회사명만으로는 통과 불가
    has_company = any(company.lower() in check_all for company in COMPANY_KEYWORDS)
    has_semicon_context = len(set(hard_hits_body)) >= 1

    if has_company and has_semicon_context and not non_semicon_hits:
        return True

    return False


def collect_direct_source_candidates(max_per_source=10):
    candidates = []
    seen = set()

    for source in DIRECT_SOURCE_URLS:
        source_name = source["name"]
        source_count = 0

        for list_url in source["urls"]:
            if source_count >= max_per_source:
                break

            try:
                res = requests.get(list_url, headers=HEADERS, timeout=12)
                res.encoding = res.apparent_encoding or res.encoding

                soup = BeautifulSoup(res.text, "html.parser")
                links = soup.select("a")

                for a in links:
                    if source_count >= max_per_source:
                        break

                    title = clean_direct_title(source_name, a)
                    href = a.get("href", "")

                    if not href:
                        continue

                    article_url = urljoin(list_url, href)

                    if article_url in seen:
                        continue

                    if not looks_like_article_url(article_url):
                        continue

                    if len(title) < 8:
                        continue

                    # 직접 크롤링 후보 단계에서는 제목에 강한 반도체 키워드가 없으면 제외
                    if not any(keyword.lower() in title.lower() for keyword in HARD_SEMICON_KEYWORDS):
                        continue
                        
                    # 후보 단계에서는 URL을 판단에 넣지 않고 제목만 봄
                    # URL의 electronics, industry 등으로 인한 오탐 방지
                    if not is_semicon_related(title, "", ""):
                        continue

                    seen.add(article_url)
                    source_count += 1

                    candidates.append({
                        "source": source_name,
                        "title": title,
                        "link": article_url
                    })

                print(f"[DIRECT] {source_name}: collected {source_count}")

                time.sleep(0.1)

            except Exception as e:
                print(f"[DIRECT ERROR] {source_name} {list_url}: {e}")

    return candidates


def fetch_news():
    global SUMMARY_CACHE
    SUMMARY_CACHE = prune_summary_cache(load_summary_cache())

    results = []
    seen_links = set()
    seen_titles = []

    stats = {
        "added": 0,
        "duplicate": 0,
        "video": 0,
        "stock": 0,
        "too_short": 0,
        "body_fallback": 0,
        "old": 0,
        "direct_candidates": 0,
        "direct_added": 0
    }

    # 1차 소스: Google News RSS
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
                title_was_foreign = is_mostly_english(title)
                title = translate_to_korean(title)
                title = remove_question_exclamation(title)

                google_link = clean_html(item.link.text if item.link else "")
                description = clean_html(item.description.text if item.description else "")
                description = strip_reporter_and_source(description)
                description = remove_title_overlap(description, title)
                pub_date = clean_html(item.pubDate.text if item.pubDate else "")

                if not is_within_recent_hours(pub_date, 24):
                    stats["old"] += 1
                    continue

                if not title or not google_link:
                    continue

                body, real_link, article_title = get_article_body(google_link)
                final_link = real_link or google_link

                if article_title and not is_bad_extracted_title(article_title):
                    title = article_title

                if final_link in seen_links:
                    stats["duplicate"] += 1
                    continue

                if len(clean_space(body)) >= 100:
                    summary_source = body
                else:
                    summary_source = description
                    stats["body_fallback"] += 1

                if len(clean_space(summary_source)) < 100:
                    stats["too_short"] += 1
                    continue

                if is_video_article(title, final_link, summary_source):
                    stats["video"] += 1
                    continue

                if is_stock_news(title, summary_source):
                    stats["stock"] += 1
                    continue

                if not is_semicon_related(title, final_link, summary_source):
                    continue

                title, summary = summarize_article(final_link, title, summary_source, translate_title=title_was_foreign)

                seen_links.add(final_link)
                seen_titles.append(title)

                published_dt = published_datetime(pub_date)

                results.append({
                    "title": title,
                    "link": final_link,
                    "short_link": short_link(final_link),
                    "summary": summary,
                    "published_ago": published_ago_from_datetime(published_dt),
                    "published_at": published_dt.isoformat(),
                    "published_raw": pub_date,
                    "published_ts": published_dt.timestamp(),
                    "body_len": len(clean_space(summary_source)),
                    "dedupe_text": summary_source[:2000]
                })

                stats["added"] += 1
                print(f"Added: {title[:45]}")

                time.sleep(0.15)

        except Exception as e:
            print(f"[ERROR] {keyword}: {e}")

    # 1.5차 소스: 영문 RSS (DigiTimes 등 — 사이트 직접 크롤링은 막혀있어 공식 RSS 이용)
    for source in ENGLISH_RSS_SOURCES:
        source_name = source["name"]
        try:
            res = requests.get(source["url"], headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.content, "xml")
            items = soup.find_all("item")

            print(f"[{source_name} RSS] items: {len(items)}")
            source_added = 0

            for item in items:
                raw_title = clean_html(item.title.text if item.title else "")
                description = clean_html(item.description.text if item.description else "")
                pub_date = clean_html(item.pubDate.text if item.pubDate else "")
                link = clean_html(item.link.text if item.link else "")

                if not link or not raw_title:
                    continue

                if not is_within_recent_hours(pub_date, 24):
                    stats["old"] += 1
                    continue

                # 번역 전에 원문(영문) 기준으로 반도체 키워드 매칭
                check_text = f"{raw_title} {description}".lower()
                if not any(keyword.lower() in check_text for keyword in HARD_SEMICON_KEYWORDS):
                    continue

                if link in seen_links:
                    stats["duplicate"] += 1
                    continue

                title = translate_to_korean(raw_title)
                title = remove_question_exclamation(title)

                # DigiTimes 기사 본문은 대부분 유료 구독 전용이라 페이지를 긁으면
                # 페이월 UI 조각(마크다운 속성 등)이 본문으로 잘못 들어오는 문제가 있었음.
                # 그래서 페이지를 따로 가져오지 않고 RSS가 제공하는 요약(teaser)을 그대로 사용한다.
                final_link = link
                summary_source = translate_to_korean(description)
                stats["body_fallback"] += 1

                if final_link in seen_links:
                    stats["duplicate"] += 1
                    continue

                if len(clean_space(summary_source)) < 80:
                    stats["too_short"] += 1
                    print(f"[{source_name} SKIP too_short] (body={len(clean_space(summary_source))}자): {title[:40]}")
                    continue

                if is_video_article(title, final_link, summary_source):
                    stats["video"] += 1
                    continue

                if is_stock_news(title, summary_source):
                    stats["stock"] += 1
                    continue

                if not is_semicon_related(title, final_link, summary_source):
                    continue

                title, summary = summarize_article(final_link, title, summary_source, translate_title=True)

                seen_links.add(final_link)
                seen_titles.append(title)

                published_dt = published_datetime(pub_date)

                results.append({
                    "title": title,
                    "link": final_link,
                    "short_link": short_link(final_link),
                    "summary": summary,
                    "published_ago": published_ago_from_datetime(published_dt),
                    "published_at": published_dt.isoformat(),
                    "published_raw": pub_date,
                    "published_ts": published_dt.timestamp(),
                    "body_len": len(clean_space(summary_source)),
                    "dedupe_text": summary_source[:2000]
                })

                stats["added"] += 1
                source_added += 1
                print(f"[{source_name} Added] {title[:45]}")

                time.sleep(0.15)

            print(f"[{source_name} RSS] added: {source_added}")

        except Exception as e:
            print(f"[{source_name} RSS ERROR]: {e}")

    # 2차 소스: 언론사 직접 크롤링 보조 소스
    direct_candidates = collect_direct_source_candidates(max_per_source=40)
    stats["direct_candidates"] = len(direct_candidates)

    for candidate in direct_candidates:
        try:
            title = candidate["title"]
            final_link = candidate["link"]

            if final_link in seen_links:
                stats["duplicate"] += 1
                continue

            body, real_link, article_title = get_article_body(final_link)
            final_link = real_link or final_link

            if article_title and not is_bad_extracted_title(article_title):
                title = article_title
            else:
                title = normalize_article_title(title)

            if final_link in seen_links:
                stats["duplicate"] += 1
                continue

            if len(clean_space(body)) < 100:
                stats["too_short"] += 1
                print(f"[DIRECT SKIP too_short] {candidate['source']} (body={len(clean_space(body))}자): {title[:40]}")
                continue

            if is_video_article(title, final_link, body):
                stats["video"] += 1
                print(f"[DIRECT SKIP video] {candidate['source']}: {title[:40]}")
                continue

            if is_stock_news(title, body):
                stats["stock"] += 1
                print(f"[DIRECT SKIP stock] {candidate['source']}: {title[:40]}")
                continue

            if not is_semicon_related(title, final_link, body):
                print(f"[DIRECT SKIP not_semicon] {candidate['source']}: {title[:40]}")
                continue

            direct_dt = get_article_published_datetime(final_link)

            if direct_dt is None:
                stats["unknown_time"] = stats.get("unknown_time", 0) + 1
                print(f"[DIRECT SKIP unknown_time] {candidate['source']}: {title[:40]} ({final_link})")
                continue

            if not is_within_recent_hours(direct_dt.isoformat(), 24):
                stats["old"] += 1
                print(f"[DIRECT SKIP old] {candidate['source']} ({direct_dt.isoformat()}): {title[:40]}")
                continue

            direct_ts = direct_dt.timestamp()
            direct_ago = published_ago_from_datetime(direct_dt)

            title, summary = summarize_article(final_link, title, body, translate_title=False)

            seen_links.add(final_link)
            seen_titles.append(title)

            results.append({
                "title": title,
                "link": final_link,
                "short_link": short_link(final_link),
                "summary": summary,
                "published_ago": direct_ago,
                "published_at": direct_dt.isoformat(),
                "published_raw": direct_dt.isoformat(),
                "published_ts": direct_ts,
                "body_len": len(clean_space(body)),
                "dedupe_text": body[:2000]
            })

            stats["added"] += 1
            stats["direct_added"] += 1
            print(f"[DIRECT Added] {candidate['source']}: {title[:45]}")

            time.sleep(0.15)

        except Exception as e:
            print(f"[DIRECT PROCESS ERROR] {candidate.get('source', '')}: {e}")

    # 내용 유사 기사 그룹은 최대 2개만 유지
    results = dedupe_by_content_keep_two(results, threshold=0.20, max_per_group=2)

    # 최신순 정렬
    results = sorted(results, key=lambda x: x.get("published_ts", 0), reverse=True)

    # 개수 제한 없음 — 24시간 내 반도체 기사는 모두 노출

    for item in results:
        item.pop("published_ts", None)
        item.pop("body_len", None)
        item.pop("dedupe_text", None)

    print("Stats:", stats)

    save_summary_cache(SUMMARY_CACHE)

    return results


ARCHIVE_DIR = os.path.join("data", "archive")
ARCHIVE_INDEX_PATH = os.path.join(ARCHIVE_DIR, "index.json")


def update_archive(news_items):
    """기사를 발행일(KST 기준) 별로 나눠서 data/archive/YYYY-MM-DD.json에 누적 저장한다.
    30분마다 도는 크론이라, 같은 날짜 파일은 기존 내용과 링크 기준으로 합쳐서(중복 제거) 계속 쌓는다."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    by_date = {}
    for item in news_items:
        published_at = item.get("published_at")
        dt = parse_datetime_safe(published_at) if published_at else None
        if dt is None:
            dt = datetime.now(timezone.utc)

        date_key = dt.astimezone(KST).strftime("%Y-%m-%d")
        by_date.setdefault(date_key, []).append(item)

    for date_key, items in by_date.items():
        day_path = os.path.join(ARCHIVE_DIR, f"{date_key}.json")

        existing = []
        if os.path.exists(day_path):
            try:
                with open(day_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        merged = {item["link"]: item for item in existing}
        for item in items:
            merged[item["link"]] = item

        merged_list = sorted(
            merged.values(),
            key=lambda x: x.get("published_at", ""),
            reverse=True
        )

        with open(day_path, "w", encoding="utf-8") as f:
            json.dump(merged_list, f, ensure_ascii=False, indent=2)

    # 인덱스 갱신 (archive 디렉터리 안의 날짜 파일들을 스캔해서 목록 생성)
    dates = []
    for filename in os.listdir(ARCHIVE_DIR):
        if not filename.endswith(".json") or filename == "index.json":
            continue

        date_key = filename[:-5]
        day_path = os.path.join(ARCHIVE_DIR, filename)

        try:
            with open(day_path, "r", encoding="utf-8") as f:
                count = len(json.load(f))
        except Exception:
            count = 0

        dates.append({"date": date_key, "count": count})

    dates = sorted(dates, key=lambda x: x["date"], reverse=True)

    with open(ARCHIVE_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(dates, f, ensure_ascii=False, indent=2)

    print(f"[ARCHIVE] {len(by_date)}개 날짜 갱신, 전체 {len(dates)}일치 보관 중")


if __name__ == "__main__":
    news = fetch_news()

    os.makedirs("data", exist_ok=True)

    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(news)} articles to data/news.json")

    update_archive(news)
