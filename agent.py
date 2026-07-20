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
    text = re.sub(r"^[=\-–]\s*", " ", text)  # 뉴시스 등 통신사 기사 앞의 '=' 표기 제거
    text = re.sub(r"\([가-힣]{2,10}=\S+\)", " ", text)  # (서울=뉴시스) 같은 통신사 표기 제거

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


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

GEMINI_MIN_INTERVAL_SECONDS = 4.5  # 무료 티어 분당 15회 제한(4초 간격) + 여유분
_last_gemini_call_at = [0.0]
GEMINI_QUOTA_EXHAUSTED = [False]  # 이번 실행(run) 동안 일일 쿼터 소진이 감지되면 True


def wait_for_gemini_rate_limit():
    elapsed = time.time() - _last_gemini_call_at[0]
    if elapsed < GEMINI_MIN_INTERVAL_SECONDS:
        time.sleep(GEMINI_MIN_INTERVAL_SECONDS - elapsed)

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


# =========================================================================
# Gemini 요약 설정 및 검증
# =========================================================================
SUMMARY_MIN_CHARS = 50
SUMMARY_MAX_CHARS = 100
SUMMARY_GENERATION_ATTEMPTS = 3
SUMMARY_RULE_VERSION = 2

# 요약이 이 단어들 중 하나로 끝나도록 제한하면 문장 중간 절단 여부를
# 코드에서 명확히 판별할 수 있다. 필요하면 서비스 문체에 맞게 추가한다.
SUMMARY_ALLOWED_ENDINGS = (
    "확대", "축소", "증가", "감소", "상승", "하락", "개선", "악화",
    "강화", "완화", "발표", "전망", "예상", "관측", "분석", "평가",
    "강조", "확인", "계획", "방침", "목표", "추진", "검토", "협력",
    "지원", "투자", "공급", "생산", "개발", "출시", "양산", "수주",
    "확보", "진입", "전환", "회복", "지속", "가속", "본격화", "가능성",
    "우려", "기대", "기대감", "주목", "유지", "집중", "부각", "시사"
)

SUMMARY_INCOMPLETE_LAST_WORDS = {
    "및", "또는", "그리고", "하지만", "다만", "따라", "통해", "위해",
    "대한", "관련", "있는", "없는", "하는", "되는", "된", "할", "될",
    "것으로", "등의", "등을", "등이", "등은", "등과", "등에"
}


def normalize_generated_text(value):
    value = clean_space(str(value or ""))
    value = re.sub(r"^(?:제목|요약)\s*[:：]\s*", "", value)
    value = value.strip("\"'“”‘’`*[]{} ")
    return clean_space(value)


def validate_summary(summary):
    """요약의 길이와 완결성을 검증해 (통과 여부, 실패 이유)를 반환한다."""
    summary = normalize_generated_text(summary)
    summary = summary.rstrip(".。!?！？ ")
    length = len(summary)

    if not summary:
        return False, "요약이 비어 있음"

    if length < SUMMARY_MIN_CHARS:
        return False, f"{length}자로 최소 {SUMMARY_MIN_CHARS}자 미달"

    if length > SUMMARY_MAX_CHARS:
        return False, f"{length}자로 최대 {SUMMARY_MAX_CHARS}자 초과"

    if summary.endswith(("…", "...", ",", "·", ":", ";", "-", "—", "(", "[")):
        return False, "문장 끝이 절단 기호로 끝남"

    last_word = summary.split()[-1].strip(".,!?;:()[]{}\"'“”‘’")
    if last_word in SUMMARY_INCOMPLETE_LAST_WORDS:
        return False, f"불완전한 마지막 단어: {last_word}"

    # 프롬프트와 코드가 같은 종료 규칙을 사용해야 잘린 문장이 통과하지 않는다.
    if not any(summary.endswith(ending) for ending in SUMMARY_ALLOWED_ENDINGS):
        return False, "허용된 명사형 종결어로 끝나지 않음"

    return True, ""


def validate_title(new_title, literal_title):
    new_title = normalize_generated_text(new_title)

    if not new_title or len(new_title) > 60:
        return None

    original_numbers = extract_numbers(literal_title)
    new_numbers = extract_numbers(new_title)
    if original_numbers and not original_numbers.issubset(new_numbers):
        return None

    return new_title


def build_summary_prompt(literal_title, body, previous_error="", previous_output=""):
    allowed_endings = ", ".join(SUMMARY_ALLOWED_ENDINGS)

    retry_instruction = ""
    if previous_error:
        retry_instruction = (
            "\n\n[이전 출력 수정 지시]\n"
            f"- 이전 오류: {previous_error}\n"
            f"- 이전 출력: {previous_output[:500]}\n"
            "- 위 오류만 고쳐 처음부터 완결된 제목과 요약을 다시 작성할 것\n"
        )

    return (
        "다음 반도체 뉴스 기사에서 한국어 헤드라인과 한 문장 요약을 작성하세요.\n\n"
        "[제목 규칙]\n"
        "- 원문 제목에 있는 사실만 사용\n"
        "- 원문 제목의 숫자는 모두 그대로 유지\n"
        "- 25~40자 권장, 최대 60자\n"
        "- 한국 경제지 헤드라인 문체로 명사형 종결\n\n"
        "[요약 규칙]\n"
        f"- 공백 포함 {SUMMARY_MIN_CHARS}~{SUMMARY_MAX_CHARS}자, 반드시 한 문장\n"
        "- 기사 핵심 사실과 주요 기업·제품·수치를 구체적으로 포함\n"
        "- 100자를 넘긴 뒤 자르지 말고 처음부터 범위 안에서 완결되게 작성\n"
        "- 마침표, 말줄임표, 콜론으로 끝내지 말 것\n"
        f"- 마지막 단어는 반드시 다음 중 하나: {allowed_endings}\n"
        "- 출력은 JSON 스키마의 title, summary 두 필드만 사용\n"
        f"{retry_instruction}\n"
        f"원문 제목: {literal_title}\n\n"
        f"기사 본문:\n{body[:3500]}"
    )


def is_daily_quota_error(response):
    error_text = (response.text or "").lower()
    daily_markers = (
        "perday", "per day", "daily", "requestsperday",
        "generaterequestsperday", "requests_per_day"
    )
    return response.status_code == 429 and any(marker in error_text for marker in daily_markers)


def request_gemini_json(prompt, max_http_attempts=3):
    """일시적 HTTP 오류만 재시도하고, 성공하면 Gemini 응답 JSON을 반환한다."""
    for http_attempt in range(1, max_http_attempts + 1):
        wait_for_gemini_rate_limit()

        try:
            response = requests.post(
                GEMINI_ENDPOINT,
                params={"key": GEMINI_API_KEY},
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 320,
                        # 짧은 요약에는 추론 토큰이 필요하지 않다. Gemini 2.5 Flash의
                        # 동적 thinking이 출력 토큰을 소모하거나 지연시키는 것을 방지한다.
                        "thinkingConfig": {"thinkingBudget": 0},
                        "responseMimeType": "application/json",
                        "responseSchema": {
                            "type": "OBJECT",
                            "properties": {
                                "title": {
                                    "type": "STRING",
                                    "description": "원문 제목 사실만 사용한 한국어 경제지 헤드라인"
                                },
                                "summary": {
                                    "type": "STRING",
                                    "description": "공백 포함 50~100자의 완결된 한국어 한 문장 요약"
                                }
                            },
                            "required": ["title", "summary"],
                            "propertyOrdering": ["title", "summary"]
                        }
                    }
                },
                timeout=30
            )
            _last_gemini_call_at[0] = time.time()

        except requests.RequestException as e:
            print(f"[Gemini HTTP ERROR] {e}")
            if http_attempt < max_http_attempts:
                time.sleep(5 * http_attempt)
                continue
            return None

        if response.status_code == 200:
            try:
                return response.json()
            except ValueError:
                print("[Gemini] HTTP 200이지만 응답 JSON 해석 실패")
                return None

        if is_daily_quota_error(response):
            print("[Gemini] 일일 쿼터 소진 감지")
            GEMINI_QUOTA_EXHAUSTED[0] = True
            return None

        if response.status_code in (429, 500, 502, 503, 504) and http_attempt < max_http_attempts:
            backoff = 6 * http_attempt
            print(f"[Gemini] 일시 오류 {response.status_code}, {backoff}초 후 재시도")
            time.sleep(backoff)
            continue

        print(f"[Gemini] 요청 실패 {response.status_code}: {response.text[:300]}")
        return None

    return None


def parse_gemini_payload(data):
    candidates = data.get("candidates", []) if isinstance(data, dict) else []
    if not candidates:
        return None, None, "응답 후보 없음"

    candidate = candidates[0]
    finish_reason = candidate.get("finishReason", "")

    if finish_reason == "MAX_TOKENS":
        return None, None, "MAX_TOKENS로 출력 중단"

    if finish_reason and finish_reason != "STOP":
        return None, None, f"finishReason={finish_reason}"

    parts = candidate.get("content", {}).get("parts", [])
    raw_text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    if not raw_text:
        return None, None, "응답 본문 없음"

    # 구조화 출력이어도 방어적으로 코드펜스를 제거한다.
    raw_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.IGNORECASE)

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return None, None, f"JSON 파싱 실패: {e.msg}"

    if not isinstance(payload, dict):
        return None, None, "JSON 최상위 값이 객체가 아님"

    title = normalize_generated_text(payload.get("title", ""))
    summary = normalize_generated_text(payload.get("summary", ""))
    summary = summary.rstrip(".。!?！？ ")

    return title, summary, ""


def summarize_with_gemini(literal_title, body):
    if not GEMINI_API_KEY or GEMINI_QUOTA_EXHAUSTED[0]:
        return None, None

    previous_error = ""
    previous_output = ""

    # HTTP 재시도와 별개로, 형식·길이·완결성 실패 시 모델 출력을 다시 생성한다.
    for generation_attempt in range(1, SUMMARY_GENERATION_ATTEMPTS + 1):
        prompt = build_summary_prompt(
            literal_title,
            body,
            previous_error=previous_error,
            previous_output=previous_output
        )
        data = request_gemini_json(prompt)
        if not data:
            return None, None

        new_title, summary, parse_error = parse_gemini_payload(data)
        if parse_error:
            previous_error = parse_error
            previous_output = ""
            print(
                f"[Gemini] 생성 {generation_attempt}/{SUMMARY_GENERATION_ATTEMPTS} 실패: "
                f"{parse_error}"
            )
            continue

        is_valid, validation_error = validate_summary(summary)
        if not is_valid:
            previous_error = validation_error
            previous_output = json.dumps(
                {"title": new_title, "summary": summary},
                ensure_ascii=False
            )
            print(
                f"[Gemini] 생성 {generation_attempt}/{SUMMARY_GENERATION_ATTEMPTS} 검증 실패: "
                f"{validation_error} / 출력={summary}"
            )
            continue

        valid_title = validate_title(new_title, literal_title)
        print(f"[Gemini] 요약 검증 통과 ({len(summary)}자)")
        return valid_title, summary

    print("[Gemini] 3회 생성 후에도 요약 조건 미충족")
    return None, None
# =========================================================================


def summarize_article(link, title, body_text, translate_title=False):
    """유효한 캐시를 우선 사용하고, 없으면 Gemini로 제목·요약을 생성한다."""
    cached = SUMMARY_CACHE.get(link)

    if cached and cached.get("summary"):
        cached_summary = normalize_generated_text(cached.get("summary", ""))
        cached_valid, _ = validate_summary(cached_summary)
        same_rule_version = cached.get("rule_version") == SUMMARY_RULE_VERSION

        if cached_valid and same_rule_version:
            final_title = cached.get("title") if (translate_title and cached.get("title")) else title
            return final_title, cached_summary

        # 예전 규칙으로 저장됐거나 잘린 요약이면 삭제하고 이번 실행에서 재생성한다.
        SUMMARY_CACHE.pop(link, None)
        print(f"[Gemini Cache] 무효 캐시 삭제 후 재생성: {link}")

    if GEMINI_QUOTA_EXHAUSTED[0]:
        return None, None

    gemini_title, summary = summarize_with_gemini(title, body_text)
    if not summary:
        return None, None

    final_title = gemini_title if (translate_title and gemini_title) else title

    SUMMARY_CACHE[link] = {
        "title": gemini_title or "",
        "summary": summary,
        "source": "gemini",
        "rule_version": SUMMARY_RULE_VERSION,
        "cached_at": datetime.now(timezone.utc).timestamp()
    }

    return final_title, summary

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
        "direct_added": 0,
        "summary_failed": 0
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

                if not summary:
                    stats["summary_failed"] = stats.get("summary_failed", 0) + 1
                    continue

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

                if not summary:
                    stats["summary_failed"] = stats.get("summary_failed", 0) + 1
                    continue

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

            if not summary:
                stats["summary_failed"] = stats.get("summary_failed", 0) + 1
                continue

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
