import logging
from flask import Blueprint, jsonify, request
from services.recommendation_service import get_recommendations

logger = logging.getLogger(__name__)
recommendations_bp = Blueprint("recommendations", __name__)


@recommendations_bp.get("/")
def list_recommendations():
    market = request.args.get("market", "KOSPI")
    top_n = min(int(request.args.get("top_n", 20)), 50)
    try:
        return jsonify(get_recommendations(market, top_n))
    except Exception as e:
        logger.exception("추천 종목 조회 실패: %s", e)
        return jsonify({"error": str(e), "recommendations": []}), 500
