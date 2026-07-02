"""
server.py — 반도체 뉴스 HTTPS 웹서버
======================================
실행:
  python server.py                     # 기본 443 포트
  python server.py --port 8443         # 포트 지정
  python server.py --http-only         # HTTP only (개발용, 80포트)
  python server.py --certbot           # Let's Encrypt 인증서 사용

도메인 없이 로컬 테스트:
  python server.py --http-only --port 8080

Let's Encrypt 사용 시 (도메인 필요):
  pip install certbot certbot-nginx
  certbot certonly --standalone -d yourdomain.com
  python server.py --certbot --domain yourdomain.com

환경변수:
  SSL_CERT   : cert.pem 경로 (기본: ./certs/cert.pem)
  SSL_KEY    : key.pem  경로 (기본: ./certs/key.pem)
  SERVER_PORT: 포트 (기본: 443)
"""

import os, ssl, argparse, subprocess, sys
from pathlib import Path
from flask import Flask, send_from_directory, jsonify, abort

BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
CERTS_DIR  = BASE_DIR / "certs"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(STATIC_DIR))

# ─── 라우트 ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """메인 페이지 — static/index.html 서빙"""
    return send_from_directory(str(BASE_DIR), "index.html")

@app.route("/api/news")
def api_news():
    """뉴스 JSON API"""
    news_file = DATA_DIR / "news.json"
    if not news_file.exists():
        return jsonify({"error": "데이터가 없습니다. agent.py 를 먼저 실행하세요."}), 404
    import json
    return app.response_class(
        response=news_file.read_text(encoding="utf-8"),
        status=200,
        mimetype="application/json",
    )

@app.route("/api/status")
def api_status():
    import json
    news_file = DATA_DIR / "news.json"
    if news_file.exists():
        data = json.loads(news_file.read_text(encoding="utf-8"))
        return jsonify({"ok": True, "generated_at": data.get("generated_at"), "total": data.get("total")})
    return jsonify({"ok": False})

@app.route("/health")
def health():
    return "OK", 200

# ─── 자가서명 인증서 생성 (openssl 필요) ─────────────────────────────────────

def generate_self_signed_cert(domain: str = "localhost") -> tuple[Path, Path]:
    cert_path = CERTS_DIR / "cert.pem"
    key_path  = CERTS_DIR / "key.pem"
    CERTS_DIR.mkdir(exist_ok=True)

    if cert_path.exists() and key_path.exists():
        print(f"  기존 인증서 사용: {cert_path}")
        return cert_path, key_path

    print(f"  자가서명 SSL 인증서 생성 중... (도메인: {domain})")
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:4096",
        "-keyout", str(key_path),
        "-out",    str(cert_path),
        "-days",   "365",
        "-nodes",
        "-subj",   f"/CN={domain}",
        "-addext", f"subjectAltName=DNS:{domain},IP:127.0.0.1",
    ], check=True, capture_output=True)
    print(f"  인증서 생성 완료: {cert_path}")
    return cert_path, key_path

def get_letsencrypt_cert(domain: str) -> tuple[Path, Path]:
    base = Path(f"/etc/letsencrypt/live/{domain}")
    return base / "fullchain.pem", base / "privkey.pem"

# ─── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port",      type=int, default=int(os.environ.get("SERVER_PORT", 443)))
    parser.add_argument("--host",      default="0.0.0.0")
    parser.add_argument("--domain",    default="localhost")
    parser.add_argument("--http-only", action="store_true", help="HTTP만 사용 (개발용)")
    parser.add_argument("--certbot",   action="store_true", help="Let's Encrypt 인증서 사용")
    args = parser.parse_args()

    print(f"\n{'='*52}")
    print(f"  반도체 뉴스 웹서버")
    print(f"{'='*52}")

    if args.http_only:
        port = args.port if args.port != 443 else 8080
        print(f"  모드: HTTP (개발용)")
        print(f"  URL : http://{args.domain}:{port}")
        print(f"{'='*52}\n")
        app.run(host=args.host, port=port, debug=False)
        return

    # HTTPS
    if args.certbot:
        cert_path, key_path = get_letsencrypt_cert(args.domain)
        print(f"  모드: HTTPS (Let's Encrypt)")
    else:
        cert_path = Path(os.environ.get("SSL_CERT", str(CERTS_DIR / "cert.pem")))
        key_path  = Path(os.environ.get("SSL_KEY",  str(CERTS_DIR / "key.pem")))
        if not cert_path.exists():
            cert_path, key_path = generate_self_signed_cert(args.domain)
        print(f"  모드: HTTPS (자가서명)")

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)

    print(f"  URL : https://{args.domain}:{args.port}")
    print(f"  Cert: {cert_path}")
    print(f"{'='*52}\n")

    import werkzeug.serving
    werkzeug.serving.run_simple(
        args.host, args.port, app,
        ssl_context=ctx,
        use_reloader=False,
        threaded=True,
    )

if __name__ == "__main__":
    main()
