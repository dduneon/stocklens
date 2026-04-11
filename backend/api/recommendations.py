from flask import Blueprint, jsonify, request
from services.recommendation_service import get_recommendations

recommendations_bp = Blueprint("recommendations", __name__)


@recommendations_bp.get("/")
def list_recommendations():
    market = request.args.get("market", "KOSPI")
    top_n = min(int(request.args.get("top_n", 20)), 50)
    return jsonify(get_recommendations(market, top_n))
