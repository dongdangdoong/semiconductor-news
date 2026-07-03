import os, json, re, hashlib, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
import feedparser

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
KST      = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
OUT_FILE = DATA_DIR / "news.json"

# ─── Google News 검색 키워드 ──────────────────────────────────────────────────
GNEWS_QUERIES = [
    "반도체", "삼성전자 반도체", "SK하이닉스", "TSMC 파운드리",
    "엔비디아 AI칩", "HBM 메모리", "반도체 장비 소재",
    "반도체 수출규제", "반도체 투자", "semiconductor chip",
    "NVIDIA GPU", "Intel chip", "ASML EUV",
]

# ─── 일반 RSS ─────────────────────────────────────────────────────────────────
RSS_SOURCES = [
    {"name": "전자신문",                 "url": "https://www.etnews.com/rss/"},
    {"name": "디일렉",                   "url": "https://www.thelec.kr/rss/"},
    {"name": "지디넷코리아",             "url": "https://zdnet.co.kr/rss.aspx"},
    {"name": "IT조선",                   "url": "https://it.chosun.com/rss/"},
    {"name": "한국경제",                 "url": "https://www.hankyung.com/feed/it"},
    {"name": "매일경제",                 "url": "https://www.mk.co.kr/rss/30100041/"},
    {"name": "EE Times",                 "url": "https://www.eetimes.com/feed/"},
    {"name": "Semiconductor Engineering","url": "https://semiengineering.com/feed/"},
    {"name": "Tom's Hardware",           "url": "https://www.tomshardware.com/feeds/all"},
    {"name": "Reuters Tech",             "url": "https://feeds.reuters.com/reuters/technologyNews"},
    {"name": "Ars Technica",             "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
]

# ─── 반도체 관련 키워드 (하나라도 있으면 수집) ───────────────────────────────
INCLUDE_KW = [
    "반도체","파운드리","메모리","웨이퍼","낸드","디램","HBM","고대역폭",
    "수율","공정","패키징","칩렛","노광","장비","소재","에칭","증착",
    "삼성전자","SK하이닉스","인텔","엔비디아","퀄컴","마이크론","TSMC","ASML",
    "수출통제","보조금","반도체법","공급망","생산능력","가동률",
    "팹리스","파운드리","후공정","전공정","전력반도체","시스템반도체",
    "semiconductor","chip","wafer","foundry","DRAM","NAND","HBM","EUV",
    "lithography","chiplet","packaging","yield","TSMC","Samsung","Intel",
    "NVIDIA","AMD","Qualcomm","Micron","SK Hynix","ASML","Applied Materials",
    "Lam Research","GPU","NPU","AI chip","supply chain","export control",
]

# ─── 주가 중심 기사 제외 ─────────────────────────────────────────────────────
STOCK_KW = [
    "주가 상승","주가 하락","주가 급등","주가 급락",
    "shares rose","shares fell","shares gained","shares dropped",
    "stock surged","stock plunged","trading higher","trading lower",
]

# ─── 제외 출처 ────────────────────────────────────────────────────────────────
EXCLUDE_SOURCES = [
    "한국방송뉴스","twig24","네이트","KBC","LG헬로비전","Vietnam.vn",
    "스페셜경제","문화일보","영남일보","Benzinga","뉴스토마토","마켓인",
    "굿모닝충청","녹색경제신문","AI타임스","코리아리포트","남해안신문",
    "청년일보","프레시안","포쓰저널","마켓잉크",
]

def strip_html(text):
    """HTML 태그 및 엔티티 제거"""
    text = text or ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&lt;","<").replace("&gt;",">").replace("&amp;","&")
    text = text.replace("&nbsp;"," ").replace("&#39;","'").replace("&quot;",'"')
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def is_valid(title, source=""):
    """수집 여부 판단"""
    # 제외 출처
    if any(s.lower() in source.lower() for s in EXCLUDE_SOURCES):
        return False
    # 반도체 키워드 없으면 제외
    combined = title.lower()
    if not any(k.lower() in combined for k in INCLUDE_KW):
        return False
    # 주가 중심 제외
    if any(k.lower() in combined for k in STOCK_KW):
        return False
    # [단독] 외 [] 괄호 있으면 제외
    brackets = re.findall(r'\[([^\]]+)\]', title)
    for b in brackets:
        if b.strip() != "단독":
            return False
    return True

def collect():
    cutoff = datetime.now(tz=KST) - timedelta(hours=24)
    articles, seen = [], set()

    # 1) Google News RSS
    for query in GNEWS_QUERIES:
        q = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
        try:
            feed = feedparser.parse(url)
            for e in feed.entries:
                pub = e.get("published_parsed") or e.get("updated_parsed")
                if not pub:
                    continue
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(KST)
                if pub_dt < cutoff:
                    continue
                title   = strip_html(e.get("title",""))
                summary = strip_html(e.get("summary","") or e.get("description",""))[:600]
                source  = strip_html(e.get("source",{}).get("title","Google News"))
                link    = e.get("link","")
                uid     = hashlib.md5(title[:60].encode()).hexdigest()[:8]
                if uid in seen or not is_valid(title, source):
                    continue
                seen.add(uid)
                articles.append({
                    "id": uid, "source": source, "title": title,
                    "content": summary, "url": link,
                    "published": pub_dt.strftime("%Y-%m-%d %H:%M"),
                    "pub_dt": pub_dt,
                })
        except Exception as ex:
            print(f"  [warn] GNews '{query}': {ex}")

    # 2) 일반 RSS
    for src in RSS_SOURCES:
        try:
            feed = feedparser.parse(src["url"])
            for e in feed.entries:
                pub = e.get("published_parsed") or e.get("updated_parsed")
                if not pub:
                    continue
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(KST)
                if pub_dt < cutoff:
                    continue
                title = strip_html(e.get("title",""))
                content = ""
                if e.get("content"):
                    content = strip_html(e["content"][0].get("value",""))
                if not content:
                    content = strip_html(e.get("summary","") or e.get("description",""))
                content = content[:600]
                link = e.get("link","")
                uid  = hashlib.md5(title[:60].encode()).hexdigest()[:8]
                if uid in seen or not is_valid(title, src["name"]):
                    continue
                seen.add(uid)
                articles.append({
                    "id": uid, "source": src["name"], "title": title,
                    "content": content, "url": link,
                    "published": pub_dt.strftime("%Y-%m-%d %H:%M"),
                    "pub_dt": pub_dt,
                })
        except Exception as ex:
            print(f"  [warn] {src['name']}: {ex}")

    # 중복 제거: 제목 앞 20자 기준, 본문 긴 것 최대 2개
    groups = {}
    for a in articles:
        key = re.sub(r"\s+","", a["title"].lower())[:20]
        groups.setdefault(key, []).append(a)

    deduped = []
    for group in groups.values():
        group.sort(key=lambda x: len(x["content"]), reverse=True)
        deduped.extend(group[:2])

    deduped.sort(key=lambda x: x["pub_dt"], reverse=True)
    for a in deduped:
        del a["pub_dt"]

    print(f"  수집 완료: {len(deduped)}건")
    return deduped

def gemini(prompt):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 300}
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    req = urllib.request.Request(url, data=body,
          headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        r = json.loads(resp.read().decode())
    return r["candidates"][0]["content"]["parts"][0]["text"].strip()

# ─── 토픽 분류 기준 ───────────────────────────────────────────────────────────
# 필터 5개: 메모리 / 비메모리 / 소부장 / 정책규제 / 투자
TOPIC_GUIDE = """
- 메모리: DRAM, NAND, HBM, 낸드, 디램, 고대역폭메모리, SK하이닉스 메모리, 마이크론
- 비메모리: 파운드리, AP, GPU, NPU, AI칩, 시스템반도체, TSMC, 팹리스, 삼성파운드리, 인텔파운드리
- 소부장: 장비, 소재, 부품, ASML, EUV, 노광, 에칭, 증착, 포토레지스트, 웨이퍼, Applied Materials, Lam Research, KLA
- 정책규제: 수출통제, 보조금, 반도체법, CHIPS Act, 규제, 제재, 관세, 정부, 외교
- 투자: 투자, M&A, 인수, 합병, 공장설립, 팹건설, 펀딩, 조인트벤처
"""

def analyze(a):
    prompt = f"""너는 반도체 전문 기자야. 아래 기사를 분석해서 반드시 정확히 5줄로만 답해.
각 줄은 "키: 값" 형식이고 다른 말은 절대 하지 마.

제목: {a['title']}
본문: {a['content'][:400]}

토픽 분류 기준:
{TOPIC_GUIDE}

TITLE_KO: (제목이 영어면 자연스러운 한국어로 번역. 한국어면 그대로.)
SUMMARY: (기사 핵심을 한글 음슴체로 80~100자. 반드시 한국어로. 예: "삼성전자가 HBM4 수율을 80%까지 높였음. 하반기 엔비디아 납품 물량이 크게 늘어날 전망임.")
COMPANY: (가장 주요한 기업명 하나. 없으면 업계전반)
TOPIC: (메모리/비메모리/소부장/정책규제/투자 중 반드시 하나만)
IMPACT: (1~5 숫자 하나만. 5=매우중요)"""

    try:
        raw = gemini(prompt)
        r = {}
        for line in raw.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                r[k.strip()] = v.strip()

        title_ko = r.get("TITLE_KO","").strip()
        summary  = r.get("SUMMARY","").strip()
        company  = r.get("COMPANY","업계전반").strip()
        topic    = r.get("TOPIC","기타").strip()
        impact_r = r.get("IMPACT","3")
        impact   = int(re.search(r'\d', impact_r).group()) if re.search(r'\d', impact_r) else 3

        # 파싱 실패 대비
        if not title_ko or len(title_ko) < 2:
            title_ko = a["title"]
        if not summary or len(summary) < 5:
            summary = a["content"][:100]
        if topic not in ["메모리","비메모리","소부장","정책규제","투자"]:
            topic = "기타"

        return {
            "id": a["id"], "title_ko": title_ko, "summary_ko": summary,
            "company": company, "topic": topic, "impact": impact,
            "source": a["source"], "url": a["url"], "published": a["published"],
        }
    except Exception as ex:
        print(f"  [warn] 분석실패 {a['id']}: {ex}")
        return {
            "id": a["id"], "title_ko": a["title"],
            "summary_ko": a["content"][:100],
            "company": "업계전반", "topic": "기타", "impact": 3,
            "source": a["source"], "url": a["url"], "published": a["published"],
        }

def run():
    print(f"API KEY: {len(GEMINI_API_KEY)}자")
    print(f"{'='*48}")
    print(f"  반도체 뉴스 에이전트  {datetime.now(tz=KST):%Y-%m-%d %H:%M KST}")
    print(f"{'='*48}")
    print("[1/2] 수집 중... (최근 24시간)")
    articles = collect()
    if not articles:
        print("  기사 없음.")
        return
    print(f"[2/2] Gemini 분석 중... ({len(articles)}건)")
    stories = []
    for i, a in enumerate(articles):
        print(f"  {i+1}/{len(articles)}: {a['title'][:45]}")
        stories.append(analyze(a))
    stories.sort(key=lambda x: x["impact"], reverse=True)
    payload = {
        "generated_at": datetime.now(tz=KST).isoformat(),
        "date":         datetime.now(tz=KST).strftime("%Y년 %m월 %d일"),
        "total":        len(stories),
        "stories":      stories,
    }
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료: {len(stories)}건\n")

if __name__ == "__main__":
    run()
