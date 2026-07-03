import os, json, re, hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import feedparser
import urllib.request

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
KST      = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
OUT_FILE = DATA_DIR / "news.json"

RSS_SOURCES = [
    {"name": "EE Times",                 "lang": "en", "url": "https://www.eetimes.com/feed/"},
    {"name": "Semiconductor Engineering","lang": "en", "url": "https://semiengineering.com/feed/"},
    {"name": "IEEE Spectrum",            "lang": "en", "url": "https://spectrum.ieee.org/feeds/feed.rss"},
    {"name": "Tom's Hardware",           "lang": "en", "url": "https://www.tomshardware.com/feeds/all"},
    {"name": "Reuters Technology",       "lang": "en", "url": "https://feeds.reuters.com/reuters/technologyNews"},
    {"name": "The Verge",                "lang": "en", "url": "https://www.theverge.com/rss/index.xml"},
    {"name": "전자신문",                 "lang": "ko", "url": "https://www.etnews.com/rss/"},
    {"name": "지디넷코리아",             "lang": "ko", "url": "https://zdnet.co.kr/rss.aspx"},
    {"name": "디일렉",                   "lang": "ko", "url": "https://www.thelec.kr/rss/"},
    {"name": "IT조선",                   "lang": "ko", "url": "https://it.chosun.com/rss/"},
    {"name": "한국경제",                 "lang": "ko", "url": "https://www.hankyung.com/feed/it"},
    {"name": "매일경제",                 "lang": "ko", "url": "https://www.mk.co.kr/rss/30100041/"},
    {"name": "네이버뉴스",               "lang": "ko", "url": "https://news.naver.com/main/rss/rss.naver?sid1=105"},
]

INCLUDE_KW = [
    "semiconductor","chip","wafer","fab","foundry","memory","DRAM","NAND","HBM",
    "EUV","ASML","lithography","process node","chiplet","TSMC","Samsung","Intel",
    "NVIDIA","AMD","Qualcomm","Micron","SK Hynix","Applied Materials","Lam Research",
    "AI chip","GPU","NPU","yield","supply chain","export control","CHIPS Act",
    "반도체","파운드리","메모리","웨이퍼","칩","낸드","디램","고대역폭",
    "수율","공정","패키징","칩렛","노광","장비","소재",
    "삼성전자","SK하이닉스","인텔","엔비디아","퀄컴","마이크론",
    "수출통제","보조금","반도체법","공급망","생산능력","가동률",
]

# 주가 중심 기사 제외 키워드
STOCK_KW = [
    "주가","주식 상승","주식 하락","코스피","코스닥","etf","펀드","증권","시총","배당","공매도",
    "stock price","share price","shares rose","shares fell","shares gained","shares dropped",
    "market cap","wall street","nasdaq","nyse","trading session",
]

def is_relevant(text):
    t = text.lower()
    if not any(k.lower() in t for k in INCLUDE_KW):
        return False
    # 주가가 주 내용인 기사 제외 (주가 키워드 3개 이상이면 제외)
    stock_hits = sum(1 for k in STOCK_KW if k.lower() in t)
    if stock_hits >= 2:
        return False
    return True

def strip_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()

def collect():
    # 24시간 이내 기사만
    cutoff = datetime.now(tz=KST) - timedelta(hours=24)
    articles, seen = [], set()

    for src in RSS_SOURCES:
        try:
            feed = feedparser.parse(src["url"])
            for e in feed.entries:
                pub    = e.get("published_parsed") or e.get("updated_parsed")
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(KST) if pub else datetime.now(tz=KST)
                if pub_dt < cutoff:
                    continue
                title   = strip_html(e.get("title","")).strip()
                # 본문 최대한 길게 확보
                summary = strip_html(
                    e.get("content",[{}])[0].get("value","") or
                    e.get("summary","") or
                    e.get("description","")
                )[:1000]
                url  = e.get("link","")
                uid  = hashlib.md5(title[:60].encode()).hexdigest()[:8]

                if uid in seen or not is_relevant(title + " " + summary):
                    continue
                seen.add(uid)
                articles.append({
                    "id":        uid,
                    "source":    src["name"],
                    "lang":      src["lang"],
                    "title":     title,
                    "summary":   summary,
                    "url":       url,
                    "published": pub_dt.strftime("%Y-%m-%d %H:%M"),
                    "pub_dt":    pub_dt,
                })
        except Exception as ex:
            print(f"  [warn] {src['name']}: {ex}")

    # 중복 기사 처리: 제목 앞 20자 기준으로 묶어서 본문 긴 것 최대 2개만 유지
    groups = {}
    for a in articles:
        key = re.sub(r"\s+","", a["title"])[:20]
        groups.setdefault(key, []).append(a)

    deduped = []
    for key, group in groups.items():
        group.sort(key=lambda x: len(x["summary"]), reverse=True)
        deduped.extend(group[:2])  # 본문 긴 것 최대 2개

    deduped.sort(key=lambda x: x["pub_dt"], reverse=True)
    # pub_dt는 직렬화 불가하므로 제거
    for a in deduped:
        del a["pub_dt"]

    print(f"  수집 완료: {len(deduped)}건 (중복 제거 후)")
    return deduped

def gemini(prompt):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300}
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()

def analyze_article(a):
    """기사 1건 분석 — 한글 음슴체 100자 요약 + 분류"""
    prompt = f"""반도체 산업 전문 기자로서 아래 기사를 분석하세요.

제목: {a['title']}
본문: {a['summary'][:600]}

아래 형식으로만 답하세요:
TITLE_KO: 한국어 제목 (영어면 자연스럽게 번역, 한국어면 그대로)
SUMMARY: 기사 첫째~둘째 문단 핵심 내용을 한글 음슴체로 100자 내외 요약. 예시: "TSMC가 2nm 공정 수율 60%를 달성했음. 애플·엔비디아에 내년 상반기 공급 예정임."
COMPANY: 주요 관련 기업 (없으면 업계전반)
TOPIC: 파운드리/메모리/AI칩/장비소재/정책규제/투자MA/공급망/기타 중 하나
IMPACT: 1~5 숫자만 (5=매우중요)"""

    try:
        raw = gemini(prompt)
        r = {}
        for line in raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                r[k.strip()] = v.strip()
        return {
            "id":        a["id"],
            "title_ko":  r.get("TITLE_KO", a["title"]),
            "summary_ko":r.get("SUMMARY", ""),
            "company":   r.get("COMPANY", ""),
            "topic":     r.get("TOPIC", "기타"),
            "impact":    int(r.get("IMPACT", "3")),
            "source":    a["source"],
            "url":       a["url"],
            "published": a["published"],
            "lang":      a["lang"],
        }
    except Exception as ex:
        print(f"  [warn] 분석 실패 {a['id']}: {ex}")
        return None

def run():
    print(f"API KEY 길이: {len(GEMINI_API_KEY)}자")
    print(f"\n{'='*48}")
    print(f"  반도체 뉴스 에이전트  {datetime.now(tz=KST):%Y-%m-%d %H:%M KST}")
    print(f"{'='*48}")

    print("[1/2] 뉴스 수집 중... (최근 24시간)")
    articles = collect()
    if not articles:
        print("  수집된 기사가 없습니다.")
        return

    print(f"[2/2] Gemini 기사별 분석 중... ({len(articles)}건)")
    stories = []
    for i, a in enumerate(articles):
        print(f"  {i+1}/{len(articles)}: {a['title'][:50]}")
        result = analyze_article(a)
        if result:
            stories.append(result)

    stories.sort(key=lambda x: x["impact"], reverse=True)

    payload = {
        "generated_at": datetime.now(tz=KST).isoformat(),
        "date":         datetime.now(tz=KST).strftime("%Y년 %m월 %d일"),
        "total":        len(stories),
        "stories":      stories,
    }
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료: {len(stories)}건 저장\n")

if __name__ == "__main__":
    run()
