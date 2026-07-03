import os, json, re, hashlib, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
import feedparser

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
KST      = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
OUT_FILE = DATA_DIR / "news.json"

GNEWS_QUERIES = [
    "반도체", "삼성전자 반도체", "SK하이닉스", "TSMC 파운드리",
    "엔비디아 AI칩", "HBM 메모리", "반도체 장비 소재",
    "반도체 수출규제", "반도체 투자", "semiconductor chip",
    "NVIDIA GPU", "Intel chip", "ASML EUV",
]

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

INCLUDE_KW = [
    "반도체","파운드리","메모리","웨이퍼","낸드","디램","HBM","고대역폭",
    "수율","공정","패키징","칩렛","노광","장비","소재","에칭","증착",
    "삼성전자","SK하이닉스","인텔","엔비디아","퀄컴","마이크론","TSMC","ASML",
    "수출통제","보조금","반도체법","공급망","생산능력","가동률",
    "팹리스","후공정","전공정","전력반도체","시스템반도체",
    "semiconductor","chip","wafer","foundry","DRAM","NAND","HBM","EUV",
    "lithography","chiplet","packaging","yield","TSMC","Samsung","Intel",
    "NVIDIA","AMD","Qualcomm","Micron","SK Hynix","ASML","Applied Materials",
    "Lam Research","GPU","NPU","AI chip","supply chain","export control",
]

STOCK_KW = [
    "주가 상승","주가 하락","주가 급등","주가 급락",
    "shares rose","shares fell","shares gained","shares dropped",
    "stock surged","stock plunged","trading higher","trading lower",
]

EXCLUDE_SOURCES = [
    "한국방송뉴스","twig24","네이트","KBC","LG헬로비전","Vietnam.vn",
    "스페셜경제","문화일보","영남일보","Benzinga","뉴스토마토","마켓인",
    "굿모닝충청","녹색경제신문","AI타임스","코리아리포트","남해안신문",
    "청년일보","프레시안","포쓰저널","마켓잉크",
]

def strip_html(text):
    text = text or ""
    text = re.sub(r"<[^>]+>", " ", text)
    for old, new in [("&lt;","<"),("&gt;",">"),("&amp;","&"),
                     ("&nbsp;"," "),("&#39;","'"),("&quot;",'"')]:
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()

def is_valid(title, source=""):
    if any(s.lower() in source.lower() for s in EXCLUDE_SOURCES):
        return False
    combined = (title + " " + source).lower()
    if not any(k.lower() in combined for k in INCLUDE_KW):
        return False
    if any(k.lower() in title.lower() for k in STOCK_KW):
        return False
    brackets = re.findall(r'\[([^\]]+)\]', title)
    for b in brackets:
        if b.strip() != "단독":
            return False
    return True

def collect():
    cutoff = datetime.now(tz=KST) - timedelta(hours=24)
    articles, seen = [], set()

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
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 400}
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    req = urllib.request.Request(url, data=body,
          headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        r = json.loads(resp.read().decode())
    return r["candidates"][0]["content"]["parts"][0]["text"].strip()

def classify_topic(title, content):
    """토픽 분류를 별도 호출로 분리 — 더 정확하게"""
    text = (title + " " + content).lower()
    # 규칙 기반 1차 분류
    memory_kw    = ["dram","nand","hbm","낸드","디램","고대역폭","메모리","sk하이닉스","마이크론","micron","hynix"]
    non_mem_kw   = ["파운드리","foundry","gpu","npu","ai chip","ai칩","팹리스","tsmc","시스템반도체","ap칩","엔비디아","nvidia","intel","amd","퀄컴","qualcomm","삼성파운드리"]
    material_kw  = ["장비","소재","부품","asml","euv","노광","에칭","증착","포토레지스트","웨이퍼","applied materials","lam research","kla","도쿄일렉트론","소부장"]
    policy_kw    = ["수출통제","보조금","반도체법","chips act","규제","제재","관세","정부","외교","export control","restriction","ban","tariff","policy"]
    invest_kw    = ["투자","m&a","인수","합병","공장","팹","건설","펀딩","조인트","joint venture","investment","acquire","merger","factory","fab"]

    scores = {
        "메모리":   sum(1 for k in memory_kw   if k in text),
        "비메모리": sum(1 for k in non_mem_kw   if k in text),
        "소부장":   sum(1 for k in material_kw  if k in text),
        "정책규제": sum(1 for k in policy_kw    if k in text),
        "투자":     sum(1 for k in invest_kw    if k in text),
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "기타"
    return best

def analyze(a):
    # 제목 번역
    if re.search(r'[a-zA-Z]{4,}', a["title"]) and not re.search(r'[가-힣]', a["title"]):
        # 영어 제목이면 번역
        title_prompt = f"아래 영어 제목을 자연스러운 한국어로 완전히 번역해. 번역문만 출력:\n{a['title']}"
        try:
            title_ko = gemini(title_prompt).strip()
        except:
            title_ko = a["title"]
    else:
        title_ko = a["title"]

    # 요약 생성
    summary_prompt = f"""아래 기사의 본문 첫째·둘째 문단 내용을 참고해서 한글 음슴체로 95~110자로 요약해.
반드시 한국어로. 숫자·수치 있으면 포함. 요약문만 출력하고 다른 말 하지 마.
예시: "삼성전자가 HBM4 수율을 80%까지 끌어올렸음. 하반기 엔비디아 납품 물량이 기존 대비 2배 이상 늘어날 전망임."

제목: {a['title']}
본문: {a['content'][:500]}"""
    try:
        summary_ko = gemini(summary_prompt).strip()
        # 너무 짧으면 재시도
        if len(summary_ko) < 30:
            summary_ko = a["content"][:100]
    except:
        summary_ko = a["content"][:100]

    # 토픽 분류 (규칙 기반)
    topic = classify_topic(a["title"], a["content"])

    # 영향도 판단
    impact_prompt = f"""아래 반도체 기사의 산업적 중요도를 1~5로 평가해. 숫자 하나만 출력.
5=매우중요(산업 판도 변화), 4=중요, 3=보통, 2=낮음, 1=매우낮음
제목: {a['title']}"""
    try:
        impact_raw = gemini(impact_prompt).strip()
        impact = int(re.search(r'[1-5]', impact_raw).group())
    except:
        impact = 3

    # 기업명 추출
    company_kw = {
        "삼성전자":"삼성전자","SK하이닉스":"SK하이닉스","TSMC":"TSMC",
        "인텔":"인텔","엔비디아":"엔비디아","AMD":"AMD","퀄컴":"퀄컴",
        "마이크론":"마이크론","ASML":"ASML","Applied Materials":"어플라이드머티리얼즈",
        "Lam Research":"램리서치","삼성":"삼성전자","nvidia":"엔비디아",
        "intel":"인텔","qualcomm":"퀄컴","micron":"마이크론",
    }
    company = "업계전반"
    combined = a["title"] + " " + a["content"]
    for kw, name in company_kw.items():
        if kw.lower() in combined.lower():
            company = name
            break

    return {
        "id":        a["id"],
        "title_ko":  title_ko,
        "summary_ko":summary_ko,
        "company":   company,
        "topic":     topic,
        "impact":    impact,
        "source":    a["source"],
        "url":       a["url"],
        "published": a["published"],
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
    print(f"[2/2] 분석 중... ({len(articles)}건)")
    stories = []
    for i, a in enumerate(articles):
        print(f"  {i+1}/{len(articles)}: {a['title'][:50]}")
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
