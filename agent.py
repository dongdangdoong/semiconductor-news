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
    {"name": "Semiconductor Engineering", "lang": "en", "url": "https://semiengineering.com/feed/"},
    {"name": "IEEE Spectrum",             "lang": "en", "url": "https://spectrum.ieee.org/feeds/feed.rss"},
    {"name": "Tom's Hardware",           "lang": "en", "url": "https://www.tomshardware.com/feeds/all"},
    {"name": "AnandTech",                "lang": "en", "url": "https://www.anandtech.com/rss/"},
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
    "stock price","share price","market cap","wall street","fell %","rose %",
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
                summary = strip_html(e.get("summary","") or e.get("description",""))[:400]
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

def analyze(articles):
    # 최대 15건만 분석 (JSON 잘림 방지)
    targets = articles[:15]
    date_str = datetime.now(tz=KST).strftime("%Y년 %m월 %d일")
    articles_text = "\n\n".join([
        f"[id:{a['id']}] [{a['source']}]\n제목: {a['title']}\n요약: {a['summary'][:200]}"
        for a in targets
    ])
    prompt = f"""반도체 산업 애널리스트로서 아래 {len(targets)}건 기사를 분석하세요.
주가 등락만 다루는 기사는 제외하고, 기술·공급망·정책 중심으로 분석하세요.

기사:
{articles_text}

아래 JSON만 출력하세요 (다른 텍스트 없이):
{{"date":"{date_str}","briefing":"핵심동향 2문장","market_signals":{{"bullish":["긍정1","긍정2"],"bearish":["부정1","부정2"],"watchlist":["주목1","주목2"]}},"stories":[{{"id":"기사id","title_ko":"한국어제목","company":"기업명","topic":"파운드리|메모리|AI칩|장비·소재|정책·규제|투자·M&A|공급망|기타","region":"한국|미국|대만|중국|일본|유럽|글로벌","insight":"의미2문장","impact":5}}]}}

stories에 {len(targets)}건 전부 포함, impact 높은 순 정렬."""

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 3000}
    }).encode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw)

def save(raw_articles, analysis):
    article_map = {a["id"]: a for a in raw_articles}
    for s in analysis.get("stories", []):
        orig = article_map.get(s.get("id"), {})
        s["source"]    = orig.get("source", "")
        s["url"]       = orig.get("url", "")
        s["published"] = orig.get("published", "")
        s["lang"]      = orig.get("lang", "ko")
    payload = {
        "generated_at": datetime.now(tz=KST).isoformat(),
        "total": len(analysis.get("stories", [])),
        **analysis,
    }
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  저장 완료: {payload['total']}건")

def run(days_back=1):
    key = os.environ.get("GEMINI_API_KEY", "")
    print(f"API KEY 길이: {len(key)}자")
    print(f"\n{'='*48}")
    print(f"  반도체 뉴스 에이전트  {datetime.now(tz=KST):%Y-%m-%d %H:%M KST}")
    print(f"{'='*48}")
    print("[1/3] 뉴스 수집 중...")
    articles = collect(days_back)
    if not articles:
        print("  수집된 기사가 없습니다.")
        return
    print(f"[2/3] Gemini 분석 중... (상위 {min(15,len(articles))}건)")
    analysis = analyze(articles)
    print("[3/3] 저장 중...")
    save(articles, analysis)
    print("완료.\n")

if __name__ == "__main__":
    run()
