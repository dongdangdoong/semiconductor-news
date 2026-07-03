import os, json, re, hashlib, urllib.parse, urllib.request, urllib.error, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import feedparser

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
KST      = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
OUT_FILE = DATA_DIR / "news.json"

# ─── RSS 소스 (안정적인 것 위주로 확대) ──────────────────────────────────────
RSS_SOURCES = [
    # 한국 반도체·IT 전문
    {"name": "전자신문",                 "url": "https://www.etnews.com/rss/"},
    {"name": "디일렉",                   "url": "https://www.thelec.kr/rss/"},
    {"name": "지디넷코리아",             "url": "https://zdnet.co.kr/rss.aspx"},
    {"name": "IT조선",                   "url": "https://it.chosun.com/rss/"},
    {"name": "아이뉴스24",               "url": "https://www.inews24.com/rss/"},
    # 한국 경제
    {"name": "한국경제",                 "url": "https://www.hankyung.com/feed/it"},
    {"name": "매일경제",                 "url": "https://www.mk.co.kr/rss/30100041/"},
    {"name": "조선비즈",                 "url": "https://biz.chosun.com/rss/"},
    {"name": "머니투데이",               "url": "https://rss.mt.co.kr/rss/0000001.xml"},
    {"name": "연합뉴스",                 "url": "https://www.yna.co.kr/rss/economy.xml"},
    # 글로벌 반도체 전문
    {"name": "EE Times",                 "url": "https://www.eetimes.com/feed/"},
    {"name": "Semiconductor Engineering","url": "https://semiengineering.com/feed/"},
    {"name": "IEEE Spectrum",            "url": "https://spectrum.ieee.org/feeds/feed.rss"},
    {"name": "Tom's Hardware",           "url": "https://www.tomshardware.com/feeds/all"},
    {"name": "AnandTech",                "url": "https://www.anandtech.com/rss/"},
    # 글로벌 기술·경제
    {"name": "Reuters Tech",             "url": "https://feeds.reuters.com/reuters/technologyNews"},
    {"name": "Ars Technica",             "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "The Verge",                "url": "https://www.theverge.com/rss/index.xml"},
    {"name": "TechCrunch",               "url": "https://techcrunch.com/feed/"},
]

# ─── 키워드 ───────────────────────────────────────────────────────────────────
INCLUDE_KW = [
    "반도체","파운드리","메모리","웨이퍼","낸드","디램","HBM","고대역폭",
    "수율","공정","패키징","칩렛","노광","장비","소재","에칭","증착",
    "삼성전자","SK하이닉스","퀄컴","마이크론","TSMC","ASML","인텔","엔비디아",
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
    "stock surged","stock plunged",
]

EXCLUDE_SOURCES = [
    "한국방송뉴스","twig24","네이트","KBC","LG헬로비전","Vietnam.vn",
    "스페셜경제","문화일보","영남일보","Benzinga","뉴스토마토","마켓인",
    "굿모닝충청","녹색경제신문","AI타임스","코리아리포트","남해안신문",
    "청년일보","프레시안","포쓰저널","마켓잉크","데일리머니","미디어펜",
    "비즈워치","아주경제","뉴스톰","v.daum.net",
]

# ─── 유틸 ─────────────────────────────────────────────────────────────────────
def strip_html(text):
    text = text or ""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>",   " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    for old, new in [("&lt;","<"),("&gt;",">"),("&amp;","&"),
                     ("&nbsp;"," "),("&#39;","'"),("&quot;",'"'),("&#8217;","'"),("&#8216;","'")]:
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

# ─── 수집 ─────────────────────────────────────────────────────────────────────
def collect():
    cutoff = datetime.now(tz=KST) - timedelta(hours=24)
    articles, seen = [], set()

    for src in RSS_SOURCES:
        try:
            feed = feedparser.parse(src["url"])
            count = 0
            for e in feed.entries:
                pub = e.get("published_parsed") or e.get("updated_parsed")
                if not pub:
                    continue
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(KST)
                if pub_dt < cutoff:
                    continue
                title = strip_html(e.get("title",""))
                # RSS 본문 최대한 확보
                content = ""
                if e.get("content"):
                    content = strip_html(e["content"][0].get("value",""))
                if not content:
                    content = strip_html(e.get("summary","") or e.get("description",""))
                content = content[:800]
                link = e.get("link","")
                uid  = hashlib.md5(title[:60].encode()).hexdigest()[:8]
                if uid in seen or not is_valid(title, src["name"]):
                    continue
                seen.add(uid)
                articles.append({
                    "id": uid, "source": src["name"],
                    "title": title, "content": content,
                    "url": link,
                    "published": pub_dt.strftime("%Y-%m-%d %H:%M"),
                    "pub_dt": pub_dt,
                })
                count += 1
            if count:
                print(f"  {src['name']}: {count}건")
        except Exception as ex:
            print(f"  [warn] {src['name']}: {ex}")

    # 중복 제거: 제목 앞 20자 기준
    groups = {}
    for a in articles:
        key = re.sub(r"\s+","", a["title"].lower())[:20]
        groups.setdefault(key, []).append(a)

    deduped = []
    for group in groups.values():
        group.sort(key=lambda x: len(x["content"]), reverse=True)
        deduped.append(group[0])

    deduped.sort(key=lambda x: x["pub_dt"], reverse=True)
    for a in deduped:
        del a["pub_dt"]

    print(f"  → 총 {len(deduped)}건 (중복제거 후)")
    return deduped

# ─── 기사 크롤링 ──────────────────────────────────────────────────────────────
def fetch_article(url, timeout=8):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")

        # 제목: og:title → title → h1
        title = ""
        for pat in [
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']',
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:title["\']',
            r'<title[^>]*>(.*?)</title>',
            r'<h1[^>]*>(.*?)</h1>',
        ]:
            m = re.search(pat, raw, re.IGNORECASE | re.DOTALL)
            if m:
                title = strip_html(m.group(1))
                if len(title) > 10:
                    break

        # 본문: article → p태그
        body = ""
        art = re.search(r'<article[^>]*>(.*?)</article>', raw, re.IGNORECASE | re.DOTALL)
        if art:
            body = strip_html(art.group(1))
        if len(body) < 100:
            paras = re.findall(r'<p[^>]*>(.*?)</p>', raw, re.IGNORECASE | re.DOTALL)
            body  = " ".join(strip_html(p) for p in paras if len(strip_html(p)) > 30)

        return title[:200], body[:800]
    except:
        return "", ""

# ─── Gemini ───────────────────────────────────────────────────────────────────
def gemini(prompt, max_tokens=500):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens}
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    req = urllib.request.Request(url, data=body,
          headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        r = json.loads(resp.read().decode())
    text = r["candidates"][0]["content"]["parts"][0]["text"].strip()
    return text

# ─── 분류 (규칙 기반) ─────────────────────────────────────────────────────────
def classify_topic(text):
    t = text.lower()
    scores = {
        "메모리":   sum(1 for k in ["dram","nand","hbm","낸드","디램","고대역폭","메모리","hynix","마이크론","micron"] if k in t),
        "비메모리": sum(1 for k in ["파운드리","foundry","gpu","npu","ai chip","ai칩","팹리스","tsmc","시스템반도체","nvidia","intel","amd","퀄컴","qualcomm","비메모리","ap칩"] if k in t),
        "소부장":   sum(1 for k in ["장비","소재","부품","asml","euv","노광","에칭","증착","포토레지스트","웨이퍼","applied materials","lam research","kla","소부장"] if k in t),
        "정책규제": sum(1 for k in ["수출통제","보조금","반도체법","chips act","규제","제재","관세","정부","외교","export control","restriction","ban","tariff","policy","sanctions"] if k in t),
        "투자":     sum(1 for k in ["투자","m&a","인수","합병","공장","팹","건설","펀딩","investment","acquire","merger","factory","fab","설립","증설"] if k in t),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "기타"

COMPANY_MAP = [
    ("삼성전자","삼성전자"),("SK하이닉스","SK하이닉스"),("sk하이닉스","SK하이닉스"),
    ("TSMC","TSMC"),("tsmc","TSMC"),("인텔","인텔"),("Intel","인텔"),
    ("엔비디아","엔비디아"),("NVIDIA","엔비디아"),("nvidia","엔비디아"),
    ("AMD","AMD"),("퀄컴","퀄컴"),("Qualcomm","퀄컴"),
    ("마이크론","마이크론"),("Micron","마이크론"),
    ("ASML","ASML"),("asml","ASML"),
    ("Applied Materials","어플라이드머티리얼즈"),
    ("Lam Research","램리서치"),
    ("앤스로픽","앤스로픽"),("Anthropic","앤스로픽"),
    ("삼성","삼성전자"),
]

def extract_company(text):
    for kw, name in COMPANY_MAP:
        if kw in text:
            return name
    return "업계전반"

def estimate_impact(text):
    t = text.lower()
    high = sum(1 for k in ["수율","독점","세계 최초","최대","돌파","혁신","ban","sanction","exclusive","record","breakthrough","world first"] if k in t)
    low  = sum(1 for k in ["전망","예정","계획","가능성","루머","rumor","plan","possible","expected"] if k in t)
    return max(1, min(5, 3 + min(high,2) - min(low,1)))

# ─── 분석 ─────────────────────────────────────────────────────────────────────
def analyze(a):
    # 1) 크롤링으로 실제 제목·본문 확보
    page_title, body = fetch_article(a["url"])
    title_raw = page_title if len(page_title) > 10 else a["title"]
    content   = body       if len(body) > 100      else a["content"]

    # 2) 제목 번역 (영어인 경우만)
    is_en = bool(re.search(r'[a-zA-Z]{4,}', title_raw)) and not bool(re.search(r'[가-힣]{3,}', title_raw))
    if is_en:
        try:
            title_ko = gemini(
                f"아래 영어 제목을 자연스럽고 완전한 한국어로 번역해. 번역문만 출력:\n{title_raw}", 150)
            print(f"     번역: {title_ko[:40]}")
        except Exception as ex:
            print(f"     번역실패: {ex}")
            title_ko = title_raw
    else:
        title_ko = title_raw

    # 3) 요약 (200~280자, 음슴체)
    try:
        summary_ko = gemini(
            f"""반도체 전문 기자로서 아래 기사를 요약해.
규칙: 한글 음슴체로 200~280자. 본문 첫째·둘째 문단 핵심만. 숫자·수치 포함. 언론사명 절대 포함 금지. 요약문만 출력.

제목: {title_raw}
본문: {content[:600]}""", 400)
        # 언론사명 후처리
        for s in [a["source"], " - " + a["source"]]:
            summary_ko = summary_ko.replace(s, "").strip()
        summary_ko = re.sub(r'\s*[-–|]\s*$', '', summary_ko).strip()
        print(f"     요약: {len(summary_ko)}자")
    except Exception as ex:
        print(f"     요약실패: {ex}")
        summary_ko = content[:200]

    # 4) 분류·기업·영향도 (규칙 기반)
    combined = title_raw + " " + content
    topic    = classify_topic(combined)
    company  = extract_company(combined)
    impact   = estimate_impact(combined)

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

# ─── 실행 ─────────────────────────────────────────────────────────────────────
def run():
    print(f"API KEY: {len(GEMINI_API_KEY)}자")
    print(f"{'='*50}")
    print(f"  반도체 뉴스 에이전트  {datetime.now(tz=KST):%Y-%m-%d %H:%M KST}")
    print(f"{'='*50}")
    print("[1/2] RSS 수집 중... (최근 24시간)")
    articles = collect()
    if not articles:
        print("  기사 없음.")
        return
    print(f"[2/2] 크롤링 + 분석 중... ({len(articles)}건)")
    stories = []
    for i, a in enumerate(articles):
        print(f"  {i+1}/{len(articles)}: {a['title'][:45]}")
        try:
            stories.append(analyze(a))
            time.sleep(0.5)
        except Exception as ex:
            print(f"    [skip] {ex}")
    stories.sort(key=lambda x: x["impact"], reverse=True)
    payload = {
        "generated_at": datetime.now(tz=KST).isoformat(),
        "date":         datetime.now(tz=KST).strftime("%Y년 %m월 %d일"),
        "total":        len(stories),
        "stories":      stories,
    }
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n완료: {len(stories)}건 저장")

if __name__ == "__main__":
    run()
