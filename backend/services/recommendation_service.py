"""투자 추천 종목 스코어링 서비스.

펀더멘털 지표(PER, PBR, DIV)와 기술적 지표(RSI, 이동평균)를 복합 채점하여
상위 종목을 추천합니다.
"""
import logging
import math
import numpy as np
from cache.ttl_cache import cache
from utils.date_utils import today_str, n_days_ago
from services.stock_service import (
    get_market_fundamental_snapshot,
    get_market_cap_snapshot,
    get_stock_ohlcv,
    get_ticker_name,
)
from config import Config

logger = logging.getLogger(__name__)

# 종목별 스코어링 가중치
W_VALUE = 0.4       # 밸류에이션 (PER, PBR)
W_DIVIDEND = 0.2    # 배당수익률
W_TECHNICAL = 0.4   # 기술적 지표 (RSI, 이동평균)


def _calc_rsi(prices: list[float], period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _calc_ma(prices: list[float], period: int) -> float | None:
    if len(prices) < period:
        return None
    return float(np.mean(prices[-period:]))


def _score_value(per: float | None, pbr: float | None) -> float:
    """밸류에이션 점수 0~100."""
    score = 50.0
    if per and per > 0:
        if per < 10:
            score += 25
        elif per < 15:
            score += 15
        elif per < 25:
            score += 5
        elif per > 50:
            score -= 20
    if pbr and pbr > 0:
        if pbr < 0.7:
            score += 20
        elif pbr < 1.0:
            score += 10
        elif pbr < 1.5:
            score += 5
        elif pbr > 5:
            score -= 15
    return max(0.0, min(100.0, score))


def _score_dividend(div: float | None) -> float:
    """배당 점수 0~100."""
    if not div or div <= 0:
        return 40.0
    if div >= 5:
        return 100.0
    if div >= 3:
        return 80.0
    if div >= 2:
        return 65.0
    return 50.0


def _score_technical(prices: list[float]) -> tuple[float, dict]:
    """기술적 점수 0~100, 세부 지표 dict 반환."""
    if len(prices) < 20:
        return 50.0, {}

    rsi = _calc_rsi(prices)
    ma5 = _calc_ma(prices, 5)
    ma20 = _calc_ma(prices, 20)
    ma60 = _calc_ma(prices, 60)
    current = prices[-1]

    score = 50.0
    signals = []

    if rsi is not None:
        if rsi < 30:
            score += 25
            signals.append(f"RSI 과매도({rsi:.1f})")
        elif rsi < 40:
            score += 10
        elif rsi > 70:
            score -= 20
            signals.append(f"RSI 과매수({rsi:.1f})")

    if ma5 and ma20:
        if ma5 > ma20:
            score += 10
            signals.append("MA5>MA20 상승추세")
        else:
            score -= 5

    if ma20 and current > 0:
        deviation = (current - ma20) / ma20 * 100
        if -5 < deviation < 5:
            score += 5  # MA20 근처 → 진입 기회

    if ma60 and current > ma60:
        score += 5

    score = max(0.0, min(100.0, score))
    return score, {
        "rsi": rsi,
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "signals": signals,
    }


def _label(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 60:
        return "buy"
    if score >= 45:
        return "watch"
    return "hold"


def score_ticker(ticker: str, fund: dict, prices: list[float]) -> dict:
    per = fund.get("per")
    pbr = fund.get("pbr")
    div = fund.get("div")

    v_score = _score_value(per, pbr)
    d_score = _score_dividend(div)
    t_score, tech_detail = _score_technical(prices)

    total = v_score * W_VALUE + d_score * W_DIVIDEND + t_score * W_TECHNICAL

    return {
        "score": round(total, 1),
        "breakdown": {
            "value": round(v_score, 1),
            "dividend": round(d_score, 1),
            "technical": round(t_score, 1),
        },
        "tech": tech_detail,
        "label": _label(total),
    }


def get_recommendations(market: str = "KOSPI", top_n: int = 20) -> dict:
    cache_key = f"recommendations:{market}:{top_n}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    date = today_str()
    fundamentals = get_market_fundamental_snapshot(date, market)
    if not fundamentals:
        return {"generated_at": date, "market": market, "recommendations": []}

    # 시가총액 상위 100개만 분석 (성능 제한)
    cap_data = get_market_cap_snapshot(date, market)
    cap_map: dict[str, float] = {
        r["ticker"]: r.get("market_cap") or 0 for r in cap_data
    }
    top_tickers = sorted(cap_map, key=lambda t: cap_map[t], reverse=True)[:100]
    top_set = set(top_tickers)

    fund_map = {
        r["ticker"]: r for r in fundamentals
        if r.get("ticker") in top_set
        and r.get("per") and r.get("per") > 0  # type: ignore[operator]
    }

    from_date = n_days_ago(120)
    results = []

    for ticker, fund in fund_map.items():
        ohlcv = get_stock_ohlcv(ticker, from_date, date)
        prices = [r["c"] for r in ohlcv if r.get("c")]

        scored = score_ticker(ticker, fund, prices)
        if scored["label"] in ("buy", "strong_buy", "watch"):
            name = get_ticker_name(ticker)
            close = prices[-1] if prices else None
            results.append({
                "ticker": ticker,
                "name": name,
                "close": close,
                "per": fund.get("per"),
                "pbr": fund.get("pbr"),
                "div": fund.get("div"),
                "market_cap": cap_map.get(ticker),
                **scored,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:top_n]
    for i, r in enumerate(results, 1):
        r["rank"] = i

    payload = {
        "generated_at": date,
        "market": market,
        "total": len(results),
        "recommendations": results,
    }
    cache.set(cache_key, payload, ttl=Config.CACHE_TTL_RECOMMENDATIONS)
    return payload
