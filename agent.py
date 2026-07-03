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

# Google News RSS — 키워드 검색 결과를 RSS로 바로 수신 (가장 안정적)
GOOGLE_NEWS_QUERIES = [
    "반도체",
    "삼성전자 반도체",
    "SK하이닉스",
    "TSMC",
    "NVIDIA chip",
    "semiconductor",
    "HBM memory",
    "AI chip semiconductor",
    "반도체 수출규제",
    "파운드리",
    "EUV ASML",
    "Intel chip",
]

# 일반 RSS 소스 (접근 가능한 것 위주)
RSS_SOURCES = [
    {"name": "전자신문",                 "lang": "ko", "url": "https://www.etnews.com/rss/"},
    {"name": "디일렉",                   "lang": "ko", "url": "https://www.thelec.kr/rss/"},
    {"name": "지디넷코리아",             "lang": "ko", "url": "https://zdnet.co.kr/rss.aspx"},
    {"name": "IT조선",                   "lang": "ko", "url": "https://it.chosun.com/rss/"},
    {"name": "한국경제",                 "lang": "ko", "url": "https://www.hankyung.com/feed/it"},
    {"name": "매일경제",                 "lang": "ko", "url": "https://www.mk.co.kr/rss/30100041/"},
    {"name": "EE Times",                 "lang": "en", "url": "https://www.eetimes.com/feed/"},
    {"name": "Semiconductor Engineering","lang": "en", "url": "https://semiengineering.com/feed/"},
    {"name": "Tom's Hardware",           "lang": "en", "url": "https://www.tomshardware.com/feeds/all"},
    {"name": "Reuters Technology",       "lang": "en", "url": "https://feeds.reuters.com/reuters/technologyNews"},
    {"name": "Ars Technica",             "lang": "en", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "The Verge",                "lang": "en", "url": "https://www.theverge.com/rss/index.xml"},
]

INCLUDE_KW = [
    "semiconductor","chip","wafer","fab","foundry","memory","DRAM","NAND","HBM",
    "EUV","ASML","lithography","process node","chiplet","TSMC","Samsung","Intel",
    "NVIDIA","AMD","Qualcomm","Micron","SK Hynix","Applied Materials","Lam Research",
    "AI chip","GPU","NPU","yield","supply chain","export control","CHIPS Act",
    "반도체","파운드리","메모리","웨이퍼","칩","낸드","디램","고대역폭","적층",
    "수율","공정","패키징","칩렛","노광","장비","소재","삼성전자","SK하이닉스",
    "인텔","엔비디아","퀄컴","마이크론","수출통제","보조금","반도체법","공급망",
    "생산능력","가동률","전력반도체","시스템반도체","팹리스","후공정","전공정",
]

STOCK_KW = [
    "주가 상승","주가 하락","주가 급등","주가 급락","주식 매수","주식 매도",
    "shares rose","shares fell","shares gained","shares dropped",
    "stock surged","stock plunged","trading higher","trading lower",
]

def is_relevant(text):
    t = text.lower()
    if not any(k.lower() in t for k in INCLUDE_KW):
        return False
    if any(k.lower() in t for k in STOCK_KW):
        return False
    return True

def strip_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()

def make_gnews_url(query):
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"

def collect():
    cutoff = datetime.now(tz=KST) - timedelta(hours=24)
    articles, seen = [], set()

    # 1) Google News RSS (키워드별)
    import urllib.parse
    for query in GOOGLE_NEWS_QUERIES:
        url = make_gnews_url(query)
        try:
            feed = feedparser.parse(url)
            for e in feed.entries:
                pub    = e.get("published_parsed") or e.get("updated_parsed")
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(KST) if pub else datetime.now(tz=KST)
                if pub_dt < cutoff:
                    continue
                title   = strip_html(e.get("title","")).strip()
                summary = strip_html(e.get("summary","") or e.get("description",""))[:600]
                url_    = e.get("link","")
                lang    = "ko" if any(ord(c) > 0x3000 for c in title) else "en"
                uid     = hashlib.md5(title[:60].encode()).hexdigest()[:8]
                if uid in seen or not is_relevant(title + " " + summary):
                    continue
                seen.add(uid)
                articles.append({
                    "id": uid, "source": f"Google News ({query})",
                    "lang": lang, "title": title, "content": summary,
                    "url": url_, "published": pub_dt.strftime("%Y-%m-%d %H:%M"),
                    "pub_dt": pub_dt,
                })
        except Exception as ex:
            print(f"  [warn] GNews '{query}': {ex}")

    # 2) 일반 RSS
    for src in RSS_SOURCES:
        try:
            feed = feedparser.parse(src["url"])
            for e in feed.entries:
                pub    = e.get("published_parsed") or e.get("updated_parsed")
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(KST) if pub else datetime.now(tz=KST)
                if pub_dt < cutoff:
                    continue
                title   = strip_html(e.get("title","")).strip()
                content = ""
                if e.get("content"):
                    content = strip_html(e["content"][0].get("value",""))
                if not content:
                    content = strip_html(e.get("summary","") or e.get("description",""))
                content = content[:600]
                url_    = e.get("link","")
                uid     = hashlib.md5(title[:60].encode()).hexdigest()[:8]
                if uid in seen or not is_relevant(title + " " + content):
                    continue
                seen.add(uid)
                articles.append({
                    "id": uid, "source": src["name"], "lang": src["lang"],
                    "title": title, "content": content, "url": url_,
                    "published": pub_dt.strftime("%Y-%m-%d %H:%M"),
                    "pub_dt": pub_dt,
                })
        except Exception as ex:
            print(f"  [warn] {src['name']}: {ex}")

    # 중복 제거: 제목 앞 15자 기준, 본문 긴 것 최대 2개
    groups = {}
    for a in articles:
        key = re.sub(r"\s+","", a["title"].lower())[:15]
        groups.setdefault(key, []).append(a)

    deduped = []
    for key, group in groups.items():
        group.sort(key=lambda x: len(x["content"]), reverse=True)
        deduped.extend(group[:2])

    deduped.sort(key=lambda x: x["pub_dt"], reverse=True)
    for a in deduped:
        del a["pub_dt"]

    print(f"  수집 완료: {len(deduped)}건 (Google News + RSS 통합)")
    return deduped

def gemini_call(prompt, max_tokens=400):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens}
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()

def analyze_article(a):
    prompt = f"""너는 반도체 산업 전문 기자야. 아래 기사를 분석해.

제목: {a['title']}
본문: {a['content'][:400]}

반드시 아래 5줄 형식으로만 답해. 콜론(:) 뒤에 바로 내용 써:
TITLE_KO: 영어면 한국어로 번역, 한국어면 그대로
SUMMARY: 핵심을 한글 음슴체로 80~100자 (예: "삼성전자가 HBM4 수율을 개선했음. 엔비디아 납품 일정이 앞당겨질 전망임.")
COMPANY: 주요 기업명 하나 (없으면 업계전반)
TOPIC: 파운드리/메모리/AI칩/장비소재/정책규제/투자MA/공급망/기타 중 하나만
IMPACT: 1에서 5 사이 숫자 하나만"""

    try:
        raw = gemini_call(prompt)
        r = {}
        for line in raw.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                r[k.strip()] = v.strip()

        title_ko = r.get("TITLE_KO","").strip() or a["title"]
        summary  = r.get("SUMMARY","").strip()  or a["content"][:100]
        company  = r.get("COMPANY","업계전반").strip()
        topic    = r.get("TOPIC","기타").strip()
        impact   = int(re.search(r'\d', r.get("IMPACT","3")).group()) if re.search(r'\d', r.get("IMPACT","3")) else 3

        return {
            "id": a["id"], "title_ko": title_ko, "summary_ko": summary,
            "company": company, "topic": topic, "impact": impact,
            "source": a["source"], "url": a["url"],
            "published": a["published"], "lang": a["lang"],
        }
    except Exception as ex:
        print(f"  [warn] 분석실패 {a['id']}: {ex}")
        return {
            "id": a["id"], "title_ko": a["title"],
            "summary_ko": a["content"][:100],
            "company": "업계전반", "topic": "기타", "impact": 3,
            "source": a["source"], "url": a["url"],
            "published": a["published"], "lang": a["lang"],
        }

def run():
    print(f"API KEY 길이: {len(GEMINI_API_KEY)}자")
    print(f"\n{'='*48}")
    print(f"  반도체 뉴스 에이전트  {datetime.now(tz=KST):%Y-%m-%d %H:%M KST}")
    print(f"{'='*48}")
    print("[1/2] 뉴스 수집 중... (최근 24시간, Google News + RSS)")
    articles = collect()
    if not articles:
        print("  수집된 기사가 없습니다.")
        return
    print(f"[2/2] Gemini 분석 중... ({len(articles)}건)")
    stories = []
    for i, a in enumerate(articles):
        print(f"  {i+1}/{len(articles)}: {a['title'][:50]}")
        stories.append(analyze_article(a))
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
