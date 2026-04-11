"""투자 추천 종목 스코어링 서비스.

5개 축(가치·수익성·성장성·수급·기술적) 복합 채점으로 상위 종목을 추천합니다.
"""
import logging
import numpy as np
from cache.ttl_cache import cache
from utils.date_utils import today_str, n_days_ago, latest_trading_date
from services.stock_service import (
    get_market_fundamental_snapshot,
    get_market_cap_snapshot,
    get_stock_ohlcv,
    get_ticker_name,
    get_investor_trading,
    get_financial_statements,
)
from config import Config

logger = logging.getLogger(__name__)

# ── 가중치 ────────────────────────────────────────────────────────────────
W_VALUE         = 0.25   # 가치 (PER·PBR·배당)
W_PROFITABILITY = 0.25   # 수익성 (ROE·영업이익률·부채비율)
W_GROWTH        = 0.15   # 성장성 (매출·영업이익 YoY)
W_FLOW          = 0.20   # 수급 (외국인·기관 순매수)
W_TECHNICAL     = 0.15   # 기술적 (RSI·이동평균·거래량)


# ── 보조 계산 ─────────────────────────────────────────────────────────────

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
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


def _calc_ma(prices: list[float], period: int) -> float | None:
    if len(prices) < period:
        return None
    return float(np.mean(prices[-period:]))


def _pct_safe(num, den) -> float | None:
    """num/den * 100, 분모가 0이거나 None이면 None."""
    if not num or not den or den == 0:
        return None
    return num / den * 100


# ── 1. 가치 점수 (0~100) ──────────────────────────────────────────────────

def _score_value(per, pbr, div, eps) -> float:
    score = 50.0

    # EPS 적자 패널티
    if eps is not None and eps <= 0:
        score -= 15

    # PER
    if per and per > 0:
        if per < 10:
            score += 25
        elif per < 15:
            score += 15
        elif per < 25:
            score += 5
        elif per > 50:
            score -= 20

    # PBR
    if pbr and pbr > 0:
        if pbr < 0.7:
            score += 20
        elif pbr < 1.0:
            score += 10
        elif pbr < 1.5:
            score += 5
        elif pbr > 5:
            score -= 15

    # 배당 보너스
    if div and div > 0:
        if div >= 5:
            score += 10
        elif div >= 3:
            score += 5

    return max(0.0, min(100.0, score))


# ── 2. 수익성 점수 (0~100) ────────────────────────────────────────────────

def _score_profitability(financials: list[dict]) -> float:
    """최신 연간 재무제표 기준 ROE·영업이익률·부채비율."""
    annuals = [f for f in financials if f.get("period_type") == "A"]
    if not annuals:
        return 40.0  # 데이터 없으면 중립

    latest = annuals[0]  # period 내림차순 정렬 가정
    score = 40.0

    # ROE = 순이익 / 자기자본
    roe = _pct_safe(latest.get("net_income"), latest.get("total_equity"))
    if roe is not None:
        if roe >= 20:
            score += 30
        elif roe >= 15:
            score += 20
        elif roe >= 10:
            score += 10
        elif roe < 0:
            score -= 20

    # 영업이익률 = 영업이익 / 매출
    op_margin = _pct_safe(latest.get("operating_income"), latest.get("revenue"))
    if op_margin is not None:
        if op_margin >= 20:
            score += 20
        elif op_margin >= 10:
            score += 12
        elif op_margin >= 5:
            score += 5
        elif op_margin < 0:
            score -= 15

    # 부채비율 = 부채 / 자기자본
    equity = latest.get("total_equity")
    debt = latest.get("total_debt")
    if equity and equity > 0 and debt is not None:
        debt_ratio = debt / equity * 100
        if debt_ratio < 50:
            score += 10
        elif debt_ratio < 100:
            score += 5
        elif debt_ratio > 200:
            score -= 10

    return max(0.0, min(100.0, score))


# ── 3. 성장성 점수 (0~100) ────────────────────────────────────────────────

def _score_growth(financials: list[dict]) -> float:
    """연간 매출·영업이익 YoY 성장률."""
    annuals = sorted(
        [f for f in financials if f.get("period_type") == "A"],
        key=lambda x: x.get("period", ""),
        reverse=True,
    )
    if len(annuals) < 2:
        return 30.0  # 비교 불가 → 중립 하향

    cur, prev = annuals[0], annuals[1]
    score = 30.0

    # 매출 성장률
    rev_growth = _pct_safe(
        (cur.get("revenue") or 0) - (prev.get("revenue") or 0),
        prev.get("revenue"),
    )
    if rev_growth is not None:
        if rev_growth >= 20:
            score += 35
        elif rev_growth >= 10:
            score += 20
        elif rev_growth >= 0:
            score += 10
        elif rev_growth < -10:
            score -= 15

    # 영업이익 성장률
    op_growth = _pct_safe(
        (cur.get("operating_income") or 0) - (prev.get("operating_income") or 0),
        prev.get("operating_income"),
    )
    if op_growth is not None:
        if op_growth >= 30:
            score += 35
        elif op_growth >= 10:
            score += 20
        elif op_growth >= 0:
            score += 10
        elif op_growth < -10:
            score -= 15

    return max(0.0, min(100.0, score))


# ── 4. 수급 점수 (0~100) ──────────────────────────────────────────────────

def _score_flow(trading: list[dict]) -> float:
    """최근 30일 외국인·기관 순매수 일수 기반."""
    if not trading:
        return 50.0

    foreign_buy_days = sum(1 for r in trading if (r.get("foreign_net") or 0) > 0)
    inst_buy_days    = sum(1 for r in trading if (r.get("institutional_net") or 0) > 0)
    total_days = len(trading)
    if total_days == 0:
        return 50.0

    foreign_ratio = foreign_buy_days / total_days
    inst_ratio    = inst_buy_days    / total_days

    score = 50.0

    # 외국인 순매수 비율
    if foreign_ratio >= 0.7:
        score += 25
    elif foreign_ratio >= 0.5:
        score += 15
    elif foreign_ratio >= 0.3:
        score += 5
    else:
        score -= 10

    # 기관 순매수 비율
    if inst_ratio >= 0.7:
        score += 25
    elif inst_ratio >= 0.5:
        score += 15
    elif inst_ratio >= 0.3:
        score += 5
    else:
        score -= 10

    return max(0.0, min(100.0, score))


# ── 5. 기술적 점수 (0~100) ────────────────────────────────────────────────

def _score_technical(prices: list[float], volumes: list[float]) -> tuple[float, dict]:
    if len(prices) < 20:
        return 50.0, {}

    rsi   = _calc_rsi(prices)
    ma5   = _calc_ma(prices, 5)
    ma20  = _calc_ma(prices, 20)
    ma60  = _calc_ma(prices, 60)
    current = prices[-1]
    score = 50.0
    signals = []

    # RSI
    if rsi is not None:
        if rsi < 30:
            score += 25
            signals.append(f"RSI 과매도({rsi:.1f})")
        elif rsi < 40:
            score += 10
        elif rsi > 70:
            score -= 20
            signals.append(f"RSI 과매수({rsi:.1f})")

    # 이동평균 추세
    if ma5 and ma20:
        if ma5 > ma20:
            score += 10
            signals.append("단기 상승추세")
        else:
            score -= 5

    if ma20 and current > 0:
        deviation = (current - ma20) / ma20 * 100
        if -5 < deviation < 5:
            score += 5

    if ma60 and current > ma60:
        score += 5

    # 52주 저가 근접 (바닥권 반등 기회)
    if len(prices) >= 60:
        low_52 = min(prices[-min(len(prices), 252):])
        if low_52 > 0 and (current - low_52) / low_52 < 0.1:
            score += 10
            signals.append("52주 저가 근접")

    # 거래량 급증 (최근 5일 평균 vs 60일 평균)
    if volumes and len(volumes) >= 60:
        vol_recent = float(np.mean(volumes[-5:]))
        vol_avg    = float(np.mean(volumes[-60:]))
        if vol_avg > 0 and vol_recent > vol_avg * 1.5:
            score += 5
            signals.append("거래량 급증")

    return max(0.0, min(100.0, score)), {
        "rsi": rsi,
        "ma5": round(ma5, 0) if ma5 else None,
        "ma20": round(ma20, 0) if ma20 else None,
        "ma60": round(ma60, 0) if ma60 else None,
        "signals": signals,
    }


# ── 레이블 ────────────────────────────────────────────────────────────────

def _label(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 60:
        return "buy"
    if score >= 45:
        return "watch"
    return "hold"


# ── 종합 스코어링 ─────────────────────────────────────────────────────────

def score_ticker(
    ticker: str,
    fund: dict,
    prices: list[float],
    volumes: list[float],
    financials: list[dict],
    trading: list[dict],
) -> dict:
    per = fund.get("per")
    pbr = fund.get("pbr")
    div = fund.get("div")
    eps = fund.get("eps")

    v_score  = _score_value(per, pbr, div, eps)
    p_score  = _score_profitability(financials)
    g_score  = _score_growth(financials)
    f_score  = _score_flow(trading)
    t_score, tech_detail = _score_technical(prices, volumes)

    total = (
        v_score  * W_VALUE
        + p_score  * W_PROFITABILITY
        + g_score  * W_GROWTH
        + f_score  * W_FLOW
        + t_score  * W_TECHNICAL
    )

    return {
        "score": round(total, 1),
        "breakdown": {
            "value":         round(v_score, 1),
            "profitability": round(p_score, 1),
            "growth":        round(g_score, 1),
            "flow":          round(f_score, 1),
            "technical":     round(t_score, 1),
        },
        "tech": tech_detail,
        "label": _label(total),
    }


# ── 추천 종목 조회 ────────────────────────────────────────────────────────

def get_recommendations(market: str = "KOSPI", top_n: int = 20) -> dict:
    cache_key = f"recommendations_v2:{market}:{top_n}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    date      = latest_trading_date()
    from_ohlcv    = n_days_ago(120)
    from_trading  = n_days_ago(30)

    fundamentals = get_market_fundamental_snapshot(date, market)
    if not fundamentals:
        return {"generated_at": date, "market": market, "recommendations": []}

    # 시가총액 상위 100개
    cap_data = get_market_cap_snapshot(date, market)
    cap_map: dict[str, float] = {
        r["ticker"]: r.get("market_cap") or 0 for r in cap_data
    }
    top_tickers = sorted(cap_map, key=lambda t: cap_map[t], reverse=True)[:100]
    top_set = set(top_tickers)

    fund_map = {
        r["ticker"]: r
        for r in fundamentals
        if r.get("ticker") in top_set
    }

    results = []
    for ticker, fund in fund_map.items():
        ohlcv      = get_stock_ohlcv(ticker, from_ohlcv, date)
        prices     = [r["c"] for r in ohlcv if r.get("c")]
        volumes    = [r["v"] for r in ohlcv if r.get("v") is not None]
        financials = get_financial_statements(ticker)
        trading    = get_investor_trading(ticker, from_trading, date)

        if len(prices) < 5:
            continue

        scored = score_ticker(ticker, fund, prices, volumes, financials, trading)

        if scored["label"] == "hold":
            continue

        name  = get_ticker_name(ticker)
        close = prices[-1]
        results.append({
            "ticker":     ticker,
            "name":       name,
            "close":      close,
            "per":        fund.get("per"),
            "pbr":        fund.get("pbr"),
            "eps":        fund.get("eps"),
            "div":        fund.get("div"),
            "market_cap": cap_map.get(ticker),
            **scored,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:top_n]
    for i, r in enumerate(results, 1):
        r["rank"] = i

    payload = {
        "generated_at": date,
        "market":       market,
        "total":        len(results),
        "recommendations": results,
    }
    cache.set(cache_key, payload, ttl=Config.CACHE_TTL_RECOMMENDATIONS)
    return payload
