"""종목 분석 + 시장 지표 API."""
import logging
from flask import Blueprint, jsonify, request
from services.analysis_service import get_stock_analysis
from services.ecos_service import get_macro_indicators
from services.shorting_service import get_market_shorting_ranking

logger = logging.getLogger(__name__)
analysis_bp = Blueprint("analysis", __name__)


@analysis_bp.get("/stocks/<ticker>")
def stock_analysis(ticker: str):
    """종목 종합 분석 (스코어링 · 목표가 · 타이밍 · 공매도 · 공시)."""
    try:
        return jsonify(get_stock_analysis(ticker))
    except Exception as e:
        logger.exception("종목 분석 실패 (%s): %s", ticker, e)
        return jsonify({"error": str(e)}), 500


@analysis_bp.get("/market/indicators")
def market_indicators():
    """ECOS 거시경제 지표 (금리 · 환율 · CPI) 시계열."""
    days = min(int(request.args.get("days", 365)), 1825)
    try:
        return jsonify(get_macro_indicators(days))
    except Exception as e:
        logger.exception("거시지표 조회 실패: %s", e)
        return jsonify({"error": str(e)}), 500


@analysis_bp.get("/market/shorting")
def market_shorting():
    """시장 공매도 비율 상위 종목."""
    market = request.args.get("market", "KOSPI")
    top_n  = min(int(request.args.get("top_n", 20)), 50)
    try:
        return jsonify({"market": market, "data": get_market_shorting_ranking(market, top_n)})
    except Exception as e:
        logger.exception("공매도 랭킹 조회 실패: %s", e)
        return jsonify({"error": str(e)}), 500
