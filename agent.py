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
EXCLUDE_KW = [
    "주가","주식","코스피","코스닥","etf","펀드","증권","시총","배당","공매도",
    "stock price","share price","market cap","wall street",
]

def is_relevant(text):
    t = text.lower()
    if not any(k.lower() in t for k in INCLUDE_KW):
        return False
    noise   = sum(1 for k in EXCLUDE_KW if k.lower() in t)
    content = sum(1 for k in INCLUDE_KW  if k.lower() in t)
    return not (noise >= 3 and content < 4)

def strip_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()

def collect(days_back=1):
    cutoff = datetime.now(tz=KST) - timedelta(days=days_back)
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
                summary = strip_html(e.get("summary","") or e.get("description",""))[:300]
                url     = e.get("link","")
                uid     = hashlib.md5(title[:60].encode()).hexdigest()[:8]
                if uid in seen or not is_relevant(title + " " + summary):
                    continue
                seen.add(uid)
                articles.append({
                    "id": uid, "source": src["name"], "lang": src["lang"],
                    "title": title, "summary": summary, "url": url,
                    "published": pub_dt.strftime("%Y-%m-%d %H:%M"),
                })
        except Exception as ex:
            print(f"  [warn] {src['name']}: {ex}")
    articles.sort(key=lambda x: x["published"], reverse=True)
    print(f"  수집 완료: {len(articles)}건")
    return articles

def gemini(prompt):
    """Gemini API 호출 — 짧은 텍스트 응답 전용"""
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800}
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()

def analyze_article(a):
    """기사 1건을 개별 분석"""
    prompt = f"""반도체 산업 애널리스트로서 아래 기사를 분석하세요.

제목: {a['title']}
내용: {a['summary']}

아래 형식으로만 답하세요(각 줄에 하나씩):
TITLE_KO: 한국어 제목
COMPANY: 주요 기업명 (없으면 업계전반)
TOPIC: 파운드리/메모리/AI칩/장비소재/정책규제/투자MA/공급망/기타 중 하나
REGION: 한국/미국/대만/중국/일본/유럽/글로벌 중 하나
INSIGHT: 산업적 의미 1~2문장
IMPACT: 1~5 숫자만"""
    try:
        raw = gemini(prompt)
        result = {}
        for line in raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                result[k.strip()] = v.strip()
        return {
            "id":       a["id"],
            "title_ko": result.get("TITLE_KO", a["title"]),
            "company":  result.get("COMPANY", ""),
            "topic":    result.get("TOPIC", "기타"),
            "region":   result.get("REGION", "글로벌"),
            "insight":  result.get("INSIGHT", ""),
            "impact":   int(result.get("IMPACT", "3")),
            "source":   a["source"],
            "url":      a["url"],
            "published":a["published"],
            "lang":     a["lang"],
        }
    except Exception as ex:
        print(f"  [warn] 분석 실패 {a['id']}: {ex}")
        return None

def make_briefing(stories):
    """전체 브리핑 요약 생성"""
    titles = "\n".join([f"- {s['title_ko']}" for s in stories[:10]])
    prompt = f"""아래 반도체 뉴스 목록을 보고 오늘의 핵심 동향을 2문장으로 요약하세요:
{titles}
요약만 출력하세요."""
    try:
        return gemini(prompt)
    except:
        return "오늘의 반도체 업계 주요 동향을 확인하세요."

def make_signals(stories):
    """마켓 시그널 생성"""
    titles = "\n".join([f"- {s['title_ko']}" for s in stories[:10]])
    prompt = f"""아래 반도체 뉴스를 보고 답하세요:
{titles}

아래 형식으로만 출력하세요:
BULL1: 긍정시그널1
BULL2: 긍정시그널2
BEAR1: 부정시그널1
BEAR2: 부정시그널2
WATCH1: 주목이슈1
WATCH2: 주목이슈2"""
    try:
        raw = gemini(prompt)
        r = {}
        for line in raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                r[k.strip()] = v.strip()
        return {
            "bullish":  [r.get("BULL1",""), r.get("BULL2","")],
            "bearish":  [r.get("BEAR1",""), r.get("BEAR2","")],
            "watchlist":[r.get("WATCH1",""), r.get("WATCH2","")],
        }
    except:
        return {"bullish":[], "bearish":[], "watchlist":[]}

def run(days_back=1):
    print(f"API KEY 길이: {len(GEMINI_API_KEY)}자")
    print(f"\n{'='*48}")
    print(f"  반도체 뉴스 에이전트  {datetime.now(tz=KST):%Y-%m-%d %H:%M KST}")
    print(f"{'='*48}")

    print("[1/3] 뉴스 수집 중...")
    articles = collect(days_back)
    if not articles:
        print("  수집된 기사가 없습니다.")
        return

    print(f"[2/3] Gemini 기사별 분석 중... ({len(articles)}건)")
    stories = []
    for i, a in enumerate(articles):
        print(f"  분석 중 {i+1}/{len(articles)}: {a['title'][:40]}")
        result = analyze_article(a)
        if result:
            stories.append(result)

    stories.sort(key=lambda x: x["impact"], reverse=True)

    print("[3/3] 브리핑 생성 및 저장 중...")
    briefing = make_briefing(stories)
    signals  = make_signals(stories)

    payload = {
        "generated_at":  datetime.now(tz=KST).isoformat(),
        "date":          datetime.now(tz=KST).strftime("%Y년 %m월 %d일"),
        "total":         len(stories),
        "briefing":      briefing,
        "market_signals":signals,
        "stories":       stories,
    }
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료: {len(stories)}건 저장\n")

if __name__ == "__main__":
    run()
