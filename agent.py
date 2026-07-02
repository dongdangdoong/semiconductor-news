"""
agent.py — 반도체 뉴스 수집 + Claude 분석
==========================================
실행:
  python agent.py           # 즉시 한 번 실행
  python agent.py --daily   # 매일 08:00 자동 실행

환경변수:
  ANTHROPIC_API_KEY  (필수)
"""

import os, json, re, time, argparse, hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import feedparser
import anthropic
import schedule

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
OUT_FILE = DATA_DIR / "news.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ─── RSS 소스 ─────────────────────────────────────────────────────────────────

RSS_SOURCES = [
    # ── 글로벌 반도체 전문 ──
    {"name": "EE Times",                "lang": "en", "url": "https://www.eetimes.com/feed/"},
    {"name": "Semiconductor Engineering","lang": "en", "url": "https://semiengineering.com/feed/"},
    {"name": "IEEE Spectrum",           "lang": "en", "url": "https://spectrum.ieee.org/feeds/feed.rss"},
    {"name": "DigiTimes",               "lang": "en", "url": "https://www.digitimes.com/rss/"},
    {"name": "Tom's Hardware",          "lang": "en", "url": "https://www.tomshardware.com/feeds/all"},
    {"name": "AnandTech",               "lang": "en", "url": "https://www.anandtech.com/rss/"},
    {"name": "SemiAnalysis",            "lang": "en", "url": "https://www.semianalysis.com/feed"},
    {"name": "WikiChip Fuse",           "lang": "en", "url": "https://fuse.wikichip.org/feed/"},
    # ── 글로벌 경제·기술 ──
    {"name": "Reuters Technology",      "lang": "en", "url": "https://feeds.reuters.com/reuters/technologyNews"},
    {"name": "The Verge",               "lang": "en", "url": "https://www.theverge.com/rss/index.xml"},
    {"name": "Ars Technica",            "lang": "en", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    # ── 한국 반도체·IT 전문 ──
    {"name": "전자신문",                "lang": "ko", "url": "https://www.etnews.com/rss/"},
    {"name": "지디넷코리아",            "lang": "ko", "url": "https://zdnet.co.kr/rss.aspx"},
    {"name": "디일렉",                  "lang": "ko", "url": "https://www.thelec.kr/rss/"},
    {"name": "IT조선",                  "lang": "ko", "url": "https://it.chosun.com/rss/"},
    {"name": "아이뉴스24",              "lang": "ko", "url": "https://www.inews24.com/rss/"},
    # ── 한국 경제·금융 ──
    {"name": "한국경제",                "lang": "ko", "url": "https://www.hankyung.com/feed/it"},
    {"name": "매일경제",                "lang": "ko", "url": "https://www.mk.co.kr/rss/30100041/"},
    # ── 네이버 뉴스 반도체 토픽 (네이버 공식 RSS) ──
    {"name": "네이버뉴스-반도체",       "lang": "ko", "url": "https://news.naver.com/main/rss/rss.naver?sid1=105"},
    {"name": "네이버뉴스-IT일반",       "lang": "ko", "url": "https://news.naver.com/main/rss/rss.naver?sid1=105&sid2=230"},
]

# ─── 키워드 필터 ──────────────────────────────────────────────────────────────

INCLUDE_KW = [
    # 영어
    "semiconductor","chip","wafer","fab","foundry","memory","DRAM","NAND","HBM",
    "EUV","ASML","lithography","process node","advanced packaging","chiplet",
    "TSMC","Samsung","Intel","NVIDIA","AMD","Qualcomm","Micron","SK Hynix",
    "Applied Materials","Lam Research","KLA","Tokyo Electron","ASML",
    "AI chip","GPU","NPU","yield","capacity","production","supply chain",
    "export control","chip act","CHIPS Act","subsidy","restriction",
    # 한국어
    "반도체","파운드리","메모리","웨이퍼","칩","낸드","디램","고대역폭","적층",
    "수율","공정","패키징","첨단패키징","칩렛","노광","장비","소재","부품",
    "삼성전자","SK하이닉스","인텔","엔비디아","퀄컴","마이크론","TSMC",
    "수출통제","보조금","반도체법","공급망","생산능력","가동률",
]

# 주가/증시 노이즈 필터 (이것만 있으면 제외)
EXCLUDE_KW = [
    "주가","주식","코스피","코스닥","etf","펀드","증권","시총","배당","공매도",
    "stock price","share price","market cap","wall street","nasdaq listed",
    "fell %","rose %","gained %","dropped %",
]

def is_relevant(text: str) -> bool:
    t = text.lower()
    if not any(k.lower() in t for k in INCLUDE_KW):
        return False
    # 주식 노이즈가 포함돼 있어도, 실질 내용 키워드가 충분하면 통과
    noise_hits  = sum(1 for k in EXCLUDE_KW if k.lower() in t)
    content_hits = sum(1 for k in INCLUDE_KW if k.lower() in t)
    return not (noise_hits >= 3 and content_hits < 4)

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()

# ─── 수집 ─────────────────────────────────────────────────────────────────────

def collect(days_back: int = 1) -> list[dict]:
    cutoff = datetime.now(tz=KST) - timedelta(days=days_back)
    articles, seen = [], set()

    for src in RSS_SOURCES:
        try:
            feed = feedparser.parse(src["url"])
            for e in feed.entries:
                pub = e.get("published_parsed") or e.get("updated_parsed")
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(KST) if pub else datetime.now(tz=KST)
                if pub_dt < cutoff:
                    continue

                title   = strip_html(e.get("title","")).strip()
                summary = strip_html(e.get("summary","") or e.get("description",""))[:600]
                url     = e.get("link","")
                uid     = hashlib.md5(title[:60].encode()).hexdigest()[:8]

                if uid in seen:
                    continue
                if not is_relevant(title + " " + summary):
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
                })
        except Exception as ex:
            print(f"  [warn] {src['name']}: {ex}")

    articles.sort(key=lambda x: x["published"], reverse=True)
    print(f"  수집 완료: {len(articles)}건")
    return articles

# ─── Claude 분석 ──────────────────────────────────────────────────────────────

ANALYSIS_PROMPT = """당신은 글로벌 반도체 산업 전문 리서치 애널리스트입니다.
아래 기사 목록을 분석하여 **산업 실질 데이터와 기술적 사실**이 포함된 기사를 중심으로 인사이트를 작성하세요.
주가 등락·시가총액 변화만 다루는 기사는 분석 대상에서 제외하세요.

기사 목록 ({n}건):
{articles}

다음 JSON 구조로만 응답하세요 (마크다운 없이 순수 JSON):
{{
  "date": "{date}",
  "briefing": "오늘 반도체 업계 핵심 동향 3~4문장 (기술·공급망·정책 중심)",
  "market_signals": {{
    "bullish": ["긍정 시그널 1", "긍정 시그널 2"],
    "bearish":  ["부정 시그널 1", "부정 시그널 2"],
    "watchlist":["주목 기업/이슈 1", "주목 기업/이슈 2"]
  }},
  "stories": [
    {{
      "id":       "원본 기사 id",
      "title_ko": "한국어 제목 (원본이 한국어면 그대로, 영어면 자연스럽게 번역)",
      "company":  "주요 관련 기업 (없으면 '업계 전반')",
      "topic":    "파운드리|메모리|AI칩|장비·소재|정책·규제|투자·M&A|공급망|기타 중 하나",
      "region":   "한국|미국|대만|중국|일본|유럽|글로벌 중 하나",
      "insight":  "이 기사의 산업적 의미, 수치·데이터 포함 2~3문장",
      "impact":   1~5
    }}
  ]
}}

stories 배열은 영향도(impact) 높은 순으로 정렬하되 건수 제한 없이 **전부** 포함하세요."""

def analyze(articles: list[dict]) -> dict:
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY 가 설정되지 않았습니다.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    date_str = datetime.now(tz=KST).strftime("%Y년 %m월 %d일")

    articles_text = "\n\n".join([
        f"[id:{a['id']}] [{a['source']}]\n제목: {a['title']}\n요약: {a['summary']}\nURL: {a['url']}"
        for a in articles
    ])

    prompt = ANALYSIS_PROMPT.format(
        n=len(articles),
        articles=articles_text,
        date=date_str,
    )

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    # 코드블록 제거
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw)

# ─── 병합 & 저장 ──────────────────────────────────────────────────────────────

def save(raw_articles: list[dict], analysis: dict):
    # analysis.stories 에 원본 url/source/published 병합
    article_map = {a["id"]: a for a in raw_articles}
    for s in analysis.get("stories", []):
        orig = article_map.get(s.get("id"), {})
        s["source"]    = orig.get("source", "")
        s["url"]       = orig.get("url", "")
        s["published"] = orig.get("published", "")
        s["lang"]      = orig.get("lang", "ko")

    payload = {
        "generated_at": datetime.now(tz=KST).isoformat(),
        "total":        len(analysis.get("stories", [])),
        **analysis,
    }
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  저장 완료: {OUT_FILE}  ({payload['total']}건)")

# ─── 실행 ─────────────────────────────────────────────────────────────────────

def run(days_back: int = 1):
    print(f"\n{'='*52}")
    print(f"  반도체 뉴스 에이전트  {datetime.now(tz=KST):%Y-%m-%d %H:%M:%S KST}")
    print(f"{'='*52}")
    print("[1/3] 뉴스 수집 중...")
    articles = collect(days_back)
    if not articles:
        print("  수집된 기사가 없습니다.")
        return
    print(f"[2/3] Claude 분석 중... ({len(articles)}건)")
    analysis = analyze(articles)
    print("[3/3] 저장 중...")
    save(articles, analysis)
    print("완료.\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily", action="store_true", help="매일 08:00 자동 실행")
    parser.add_argument("--days",  type=int, default=1)
    args = parser.parse_args()

    if args.daily:
        print("스케줄러 시작 — 매일 08:00 실행")
        run(args.days)
        schedule.every().day.at("08:00").do(run, days_back=args.days)
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        run(args.days)
