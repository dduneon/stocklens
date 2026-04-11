from flask import Blueprint, jsonify, request
from services.market_service import get_market_summary, get_index_chart

market_bp = Blueprint("market", __name__)


@market_bp.get("/summary")
def summary():
    market = request.args.get("market", "KOSPI")
    return jsonify(get_market_summary(market))


@market_bp.get("/index-chart")
def index_chart():
    market = request.args.get("market", "KOSPI")
    days = min(int(request.args.get("days", 90)), 365)
    return jsonify(get_index_chart(market, days))
