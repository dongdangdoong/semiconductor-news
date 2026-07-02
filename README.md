# 반도체 뉴스 브리핑 — 설치 & 실행 가이드

## 파일 구조
```
semiconductor_news/
├── agent.py          ← 뉴스 수집 + Claude 분석
├── server.py         ← HTTPS 웹서버
├── index.html        ← 웹페이지 프론트엔드
├── requirements.txt
├── data/
│   └── news.json     ← agent.py 실행 후 생성됨
└── certs/
    ├── cert.pem      ← SSL 인증서 (자동 생성)
    └── key.pem       ← SSL 개인키 (자동 생성)
```

---

## 1. 설치

```bash
pip install -r requirements.txt
```

openssl 이 없다면 (Ubuntu/Debian):
```bash
sudo apt install openssl
```

---

## 2. 환경변수 설정

```bash
export ANTHROPIC_API_KEY="sk-ant-..."      # 필수

# 선택 사항
export SERVER_PORT=443
export SSL_CERT=/path/to/cert.pem          # 직접 인증서 지정 시
export SSL_KEY=/path/to/key.pem
```

---

## 3. 실행 방법

### A. 개발/테스트 (HTTP, 8080 포트)
```bash
# 터미널 1 — 뉴스 수집
python agent.py

# 터미널 2 — 웹서버
python server.py --http-only --port 8080

# 브라우저 → http://localhost:8080
```

### B. 운영 (HTTPS, 자가서명 인증서)
```bash
# 뉴스 수집 (최초 1회)
python agent.py

# 웹서버 실행 (root 권한 필요 — 443 포트)
sudo python server.py --domain yourdomain.com

# 브라우저 → https://yourdomain.com
# ※ 자가서명 인증서 경고는 "고급 → 계속 진행"으로 무시
```

### C. 운영 (HTTPS, Let's Encrypt 공인 인증서)
도메인이 있어야 합니다.
```bash
# certbot 설치 & 인증서 발급
sudo apt install certbot
sudo certbot certonly --standalone -d yourdomain.com

# 웹서버 실행
sudo python server.py --certbot --domain yourdomain.com
```

### D. 매일 아침 자동 실행 (cron)
```bash
# crontab -e
0 8 * * * /usr/bin/python3 /path/to/semiconductor_news/agent.py >> /var/log/semi_news.log 2>&1
```

또는 데몬 모드:
```bash
python agent.py --daily &   # 백그라운드 실행, 매일 08:00 자동 수집
```

---

## 4. API 엔드포인트

| 경로 | 설명 |
|------|------|
| `GET /` | 웹페이지 |
| `GET /api/news` | 뉴스 JSON 데이터 |
| `GET /api/status` | 업데이트 시각·건수 |
| `GET /health` | 서버 상태 확인 |

---

## 5. 뉴스 소스 목록

**글로벌 반도체 전문**
- EE Times, Semiconductor Engineering, IEEE Spectrum
- DigiTimes, Tom's Hardware, AnandTech, SemiAnalysis, WikiChip Fuse

**글로벌 경제·기술**
- Reuters Technology, The Verge, Ars Technica

**한국 반도체·IT 전문**
- 전자신문, 지디넷코리아, 디일렉(The Elec), IT조선, 아이뉴스24

**한국 경제**
- 한국경제, 매일경제

**네이버 뉴스**
- 네이버뉴스 반도체 토픽, IT일반 토픽

---

## 6. 필터링 정책

- **포함**: 기술 공정·수율·장비·공급망·정책·투자·M&A 관련 실질 데이터가 있는 기사
- **제외**: 주가 등락, 시총, ETF, 배당 등 순수 주식 정보만 담긴 기사
- **영향도 (H5~L1)**: Claude가 산업적 중요도를 1~5로 평가
