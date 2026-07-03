import os, json, re, hashlib, urllib.parse, urllib.request, urllib.error, time
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
    {"name": "한국경제",                 "url": "https://www.hankyung.com/feed/it"},
    {"name": "매일경제",                 "url": "https://www.mk.co.kr/rss/30100041/"},
    {"name": "EE Times",                 "url": "https://www.eetimes.com/feed/"},
    {"name": "Semiconductor Engineering","url": "https://semiengineering.com/feed/"},
    {"name": "Reuters Tech",             "url": "https://feeds.reuters.com/reuters/technologyNews"},
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
    "stock surged","stock plunged",
]

EXCLUDE_SOURCES = [
    "한국방송뉴스","twig24","네이트","KBC","LG헬로비전","Vietnam.vn",
    "스페셜경제","문화일보","영남일보","Benzinga","뉴스토마토","마켓인",
    "굿모닝충청","녹색경제신문","AI타임스","코리아리포트","남해안신문",
    "청년일보","프레시안","포쓰저널","마켓잉크","데일리머니","미디어펜",
    "비즈워치","아주경제","뉴스톰","v.daum.net",
]

# ─── HTML 파싱 ────────────────────────────────────────────────────────────────

def strip_html(text):
    text = text or ""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>",  " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    for old, new in [("&lt;","<"),("&gt;",">"),("&amp;","&"),
                     ("&nbsp;"," "),("&#39;","'"),("&quot;",'"')]:
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()

def fetch_article(url, timeout=8):
    """기사 URL에서 제목과 본문 첫 500자 추출"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")

        # 제목 추출: og:title → <title> → <h1> 순
        title = ""
        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', raw, re.IGNORECASE)
        if m:
            title = strip_html(m.group(1))
        if not title:
            m = re.search(r'<title[^>]*>(.*?)</title>', raw, re.IGNORECASE | re.DOTALL)
            if m:
                title = strip_html(m.group(1))
        if not title:
            m = re.search(r'<h1[^>]*>(.*?)</h1>', raw, re.IGNORECASE | re.DOTALL)
            if m:
                title = strip_html(m.group(1))

        # 본문 추출: article 태그 → p 태그들
        body = ""
        art = re.search(r'<article[^>]*>(.*?)</article>', raw, re.IGNORECASE | re.DOTALL)
        if art:
            body = strip_html(art.group(1))
        if not body or len(body) < 50:
            # p 태그에서 추출
            paras = re.findall(r'<p[^>]*>(.*?)</p>', raw, re.IGNORECASE | re.DOTALL)
            body = " ".join(strip_html(p) for p in paras if len(strip_html(p)) > 30)

        return title[:200], body[:800]
    except Exception:
        return "", ""

# ─── 수집 ─────────────────────────────────────────────────────────────────────

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

    # Google News RSS
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
                rss_title = strip_html(e.get("title",""))
                source    = strip_html(e.get("source",{}).get("title","Google News"))
                link      = e.get("link","")
                uid       = hashlib.md5(rss_title[:60].encode()).hexdigest()[:8]
                if uid in seen or not is_valid(rss_title, source):
                    continue
                seen.add(uid)
                articles.append({
                    "id": uid, "source": source,
                    "rss_title": rss_title, "url": link,
                    "published": pub_dt.strftime("%Y-%m-%d %H:%M"),
                    "pub_dt": pub_dt,
                })
        except Exception as ex:
            print(f"  [warn] GNews '{query}': {ex}")

    # 일반 RSS
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
                rss_title = strip_html(e.get("title",""))
                link      = e.get("link","")
                uid       = hashlib.md5(rss_title[:60].encode()).hexdigest()[:8]
                if uid in seen or not is_valid(rss_title, src["name"]):
                    continue
                seen.add(uid)
                articles.append({
                    "id": uid, "source": src["name"],
                    "rss_title": rss_title, "url": link,
                    "published": pub_dt.strftime("%Y-%m-%d %H:%M"),
                    "pub_dt": pub_dt,
                })
        except Exception as ex:
            print(f"  [warn] {src['name']}: {ex}")

    # 중복 제거
    groups = {}
    for a in articles:
        key = re.sub(r"\s+","", a["rss_title"].lower())[:20]
        groups.setdefault(key, []).append(a)

    deduped = []
    for group in groups.values():
        deduped.append(group[0])

    deduped.sort(key=lambda x: x["pub_dt"], reverse=True)
    for a in deduped:
        del a["pub_dt"]

    print(f"  RSS 수집 완료: {len(deduped)}건")
    return deduped

# ─── 토픽 분류 (규칙 기반) ───────────────────────────────────────────────────

def classify_topic(text):
    text = text.lower()
    scores = {
        "메모리":   sum(1 for k in ["dram","nand","hbm","낸드","디램","고대역폭","메모리","hynix","마이크론","micron"] if k in text),
        "비메모리": sum(1 for k in ["파운드리","foundry","gpu","npu","ai chip","ai칩","팹리스","tsmc","시스템반도체","nvidia","intel","amd","퀄컴","qualcomm","삼성파운드리","비메모리"] if k in text),
        "소부장":   sum(1 for k in ["장비","소재","부품","asml","euv","노광","에칭","증착","포토레지스트","웨이퍼","applied materials","lam research","kla","소부장"] if k in text),
        "정책규제": sum(1 for k in ["수출통제","보조금","반도체법","chips act","규제","제재","관세","정부","외교","export control","restriction","ban","tariff","policy","sanctions"] if k in text),
        "투자":     sum(1 for k in ["투자","m&a","인수","합병","공장","팹","건설","펀딩","조인트","investment","acquire","merger","factory","fab","설립","증설"] if k in text),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "기타"

# ─── Gemini 호출 ─────────────────────────────────────────────────────────────

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
    return r["candidates"][0]["content"]["parts"][0]["text"].strip()

# ─── 기업명 추출 (규칙 기반) ─────────────────────────────────────────────────

COMPANY_MAP = [
    ("삼성전자","삼성전자"), ("SK하이닉스","SK하이닉스"), ("sk하이닉스","SK하이닉스"),
    ("TSMC","TSMC"), ("tsmc","TSMC"), ("인텔","인텔"), ("Intel","인텔"),
    ("엔비디아","엔비디아"), ("NVIDIA","엔비디아"), ("nvidia","엔비디아"),
    ("AMD","AMD"), ("퀄컴","퀄컴"), ("Qualcomm","퀄컴"), ("마이크론","마이크론"),
    ("Micron","마이크론"), ("ASML","ASML"), ("asml","ASML"),
    ("어플라이드","어플라이드머티리얼즈"), ("Applied Materials","어플라이드머티리얼즈"),
    ("램리서치","램리서치"), ("Lam Research","램리서치"),
    ("인피니언","인피니언"), ("르네사스","르네사스"), ("앤스로픽","앤스로픽"),
    ("Anthropic","앤스로픽"), ("삼성","삼성전자"),
]

def extract_company(text):
    for kw, name in COMPANY_MAP:
        if kw in text:
            return name
    return "업계전반"

# ─── 영향도 판단 (규칙 기반) ─────────────────────────────────────────────────

def estimate_impact(title, body):
    text = (title + " " + body).lower()
    high_kw = ["수율","공급 계약","독점","세계 최초","최대","최고","돌파","혁신",
                "yield","exclusive","world first","record","breakthrough","ban","sanction"]
    low_kw  = ["일정","계획","예정","전망","루머","관측","가능성",
                "schedule","plan","rumor","speculation","possible"]
    h = sum(1 for k in high_kw if k in text)
    l = sum(1 for k in low_kw  if k in text)
    score = 3 + min(h, 2) - min(l, 1)
    return max(1, min(5, score))

# ─── 분석 ────────────────────────────────────────────────────────────────────

def analyze(a):
    # 1) 실제 기사 페이지 크롤링
    print(f"     크롤링 중: {a['url'][:60]}")
    page_title, body = fetch_article(a["url"])

    # 제목: 크롤링 성공하면 실제 제목, 아니면 RSS 제목
    title_raw = page_title if len(page_title) > 10 else a["rss_title"]

    # 영어 제목이면 Gemini로 번역
    is_english = bool(re.search(r'[a-zA-Z]{4,}', title_raw)) and not bool(re.search(r'[가-힣]{3,}', title_raw))
    if is_english:
        try:
            title_ko = gemini(f"아래 영어 제목을 자연스러운 한국어로 완역해. 번역문만 출력:\n{title_raw}", 200)
        except:
            title_ko = title_raw
    else:
        title_ko = title_raw

    # 2) 요약: 크롤링된 본문 or RSS 미리보기
    content_for_summary = body if len(body) > 100 else a.get("rss_title","")
    try:
        summary_ko = gemini(
            f"""아래 기사 본문의 첫째·둘째 문단 핵심 내용을 한글 음슴체로 200~280자로 요약해.
숫자·수치·기업명 있으면 반드시 포함. 요약문만 출력. 언론사 이름 절대 포함하지 말 것.
예시: "삼성전자가 HBM4 수율을 80%까지 끌어올렸음. 기존 60% 대비 크게 개선된 수치로, 엔비디아의 블랙웰 GPU에 탑재될 HBM4 공급을 위한 핵심 조건을 충족한 것으로 알려짐. 하반기 납품 물량이 기존 계획 대비 2배 이상 늘어날 전망임."

기사 제목: {title_raw}
기사 본문: {content_for_summary[:600]}""", 400)
        # 언론사명 후처리 제거
        for src_name in [a["source"], "- " + a["source"]]:
            summary_ko = summary_ko.replace(src_name, "").strip()
        summary_ko = re.sub(r'\s*[-–]\s*$', '', summary_ko).strip()
    except:
        summary_ko = content_for_summary[:200]

    # 3) 토픽·기업·영향도 (규칙 기반)
    combined   = title_raw + " " + content_for_summary
    topic      = classify_topic(combined)
    company    = extract_company(combined)
    impact     = estimate_impact(title_raw, content_for_summary)

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

# ─── 실행 ────────────────────────────────────────────────────────────────────

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
    print(f"[2/2] 기사별 크롤링 + 분석 중... ({len(articles)}건)")
    stories = []
    for i, a in enumerate(articles):
        print(f"  {i+1}/{len(articles)}: {a['rss_title'][:45]}")
        try:
            stories.append(analyze(a))
            time.sleep(0.3)  # 크롤링 간격
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
