"""StockLens Flask 애플리케이션 팩토리."""
import sys
import os
import logging

# backend/ 디렉토리를 sys.path에 추가
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from config import Config
from krx_session.manager import login_krx, is_logged_in
from db.engine import ping as db_ping

logging.basicConfig(
    level=logging.DEBUG if Config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
    app = Flask(__name__, static_folder=None)
    app.secret_key = Config.SECRET_KEY
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # ── API 블루프린트 등록 ────────────────────────────────────────────
    from api.market import market_bp
    from api.stocks import stocks_bp
    from api.recommendations import recommendations_bp

    app.register_blueprint(market_bp, url_prefix="/api/market")
    app.register_blueprint(stocks_bp, url_prefix="/api/stocks")
    app.register_blueprint(recommendations_bp, url_prefix="/api/recommendations")

    # ── 상태 엔드포인트 ───────────────────────────────────────────────
    @app.get("/api/session/status")
    def session_status():
        return jsonify({
            "logged_in": is_logged_in(),
            "db": db_ping(),
        })

    # ── 프론트엔드 정적 파일 서빙 ─────────────────────────────────────
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path: str):
        if path.startswith("api/"):
            return jsonify({"error": "not found"}), 404
        target = os.path.join(frontend_dir, path)
        if path and os.path.isfile(target):
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, "index.html")

    # ── 에러 핸들러 ───────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.error("Internal error: %s", e)
        return jsonify({"error": "internal server error"}), 500

    return app


if __name__ == "__main__":
    if not Config.KRX_LOGIN_ID or not Config.KRX_LOGIN_PW:
        logger.error(".env 파일에 KRX_LOGIN_ID, KRX_LOGIN_PW를 설정하세요.")
        sys.exit(1)

    logger.info("KRX 로그인 시도...")
    if not login_krx(Config.KRX_LOGIN_ID, Config.KRX_LOGIN_PW):
        logger.error("KRX 로그인 실패. 자격증명을 확인하세요.")
        sys.exit(1)

    app = create_app()
    app.run(
        host="0.0.0.0",
        port=Config.PORT,
        debug=Config.DEBUG,
        use_reloader=False,  # 세션 재로그인 방지
    )
