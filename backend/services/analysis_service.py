"""종목 종합 분석 서비스.

제공 분석:
  - 5축 스코어링 (recommendation_service 재활용)
  - 목표가 추정 (PER / PBR / Forward P/E / 52주 기반)
  - 매수 타이밍 시그널 (RSI · 이동평균 · 볼린저밴드)
  - 공매도 요약
  - 최근 DART 공시
  - 거시지표 참고값
"""
import logging
import numpy as np

from cache.ttl_cache import cache
from config import Config
from utils.date_utils import n_days_ago, latest_trading_date
from services.stock_service import (
    get_stock_ohlcv, get_stock_fundamental, get_financial_statements,
    get_investor_trading, get_ticker_name, get_market_fundamental_snapshot,
    get_market_cap_snapshot,
)
from services.recommendation_service import score_ticker
from services.shorting_service import get_shorting_summary
from services.disclosure_service import get_disclosures
from services.ecos_service import get_latest_macro

logger = logging.getLogger(__name__)


# ── 내부 유틸 ─────────────────────────────────────────────────────────────

def _ma(prices: list[float], n: int) -> float | None:
    if len(prices) < n:
        return None
    return float(np.mean(prices[-n:]))


def _rsi(prices: list[float], period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_g  = np.mean(gains[:period])
    avg_l  = np.mean(losses[:period])
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_g / avg_l), 2)


def _bollinger(prices: list[float], n: int = 20) -> tuple[float | None, float | None]:
    """(하단밴드, 상단밴드) 반환."""
    if len(prices) < n:
        return None, None
    window = prices[-n:]
    mid = float(np.mean(window))
    std = float(np.std(window))
    return round(mid - 2 * std, 0), round(mid + 2 * std, 0)


def _safe_pct(num, den) -> float | None:
    if not num or not den or den == 0:
        return None
    return round(num / den * 100, 2)


# ── 목표가 계산 ───────────────────────────────────────────────────────────

def _calculate_target_price(prices: list[float], fund: dict,
                             financials: list[dict]) -> dict:
    current = prices[-1] if prices else None
    if not current:
        return {}

    targets = {}

    per   = fund.get("per")
    pbr   = fund.get("pbr")
    eps   = fund.get("eps")
    bps   = fund.get("bps")

    # ① PER 기반: EPS × 적정 PER(15 — 한국 시장 장기 평균)
    if eps and eps > 0:
        fair_per = 15.0
        targets["per_based"] = round(eps * fair_per, 0)

    # ② PBR 기반: BPS × 1.0 (청산가치 = 최소 목표가)
    if bps and bps > 0:
        targets["pbr_based"] = round(bps * 1.0, 0)

    # ③ Forward P/E 기반
    fwd_pe = _calculate_forward_pe(current, fund, financials)
    if fwd_pe.get("forward_eps") and fwd_pe["forward_eps"] > 0:
        targets["forward_per_based"] = round(fwd_pe["forward_eps"] * 15.0, 0)

    # ④ 52주 기반: (52주 고가 + 저가) / 2
    if len(prices) >= 60:
        window = prices[-min(len(prices), 252):]
        hi52 = max(window)
        lo52 = min(window)
        targets["week52_mid"] = round((hi52 + lo52) / 2, 0)

    if not targets:
        return {"current": current}

    # 컨센서스: 유효한 목표가들의 평균
    valid = [v for v in targets.values() if v and v > 0]
    consensus = round(float(np.mean(valid)), 0) if valid else None
    upside    = _safe_pct(consensus - current, current) if consensus else None

    return {
        "current":            current,
        **targets,
        "consensus":          consensus,
        "upside_pct":         upside,
    }


# ── Forward P/E ───────────────────────────────────────────────────────────

def _calculate_forward_pe(current_price: float, fund: dict,
                           financials: list[dict]) -> dict:
    """예상 EPS 기반 Forward P/E 계산.

    연간 재무제표(A)에서 최신 2개년 순이익 YoY 성장률을 구해
    forward EPS = 최신 EPS × (1 + 성장률) 로 추정.

    한계: 애널리스트 컨센서스(Fnguide 등)의 Forward EPS와 다를 수 있음.
    특히 실적 턴어라운드 종목(삼성전자 등)은 과거 YoY 방식이 미래를 크게 과소평가함.
    """
    eps = fund.get("eps")
    per = fund.get("per")

    # 연간 재무제표만, 최신순 정렬, 순이익이 있는 것만
    annuals = sorted(
        [f for f in financials
         if f.get("period_type") == "A" and f.get("net_income")],
        key=lambda x: x.get("period", ""),
        reverse=True,
    )

    growth_rate = None
    latest_ni   = None
    base_period = None

    if len(annuals) >= 2:
        ni_cur  = annuals[0].get("net_income")
        ni_prev = annuals[1].get("net_income")
        latest_ni   = ni_cur
        base_period = annuals[0].get("period", "")
        if ni_cur and ni_prev and ni_prev != 0:
            growth_rate = (ni_cur - ni_prev) / abs(ni_prev)
            growth_rate = max(-0.5, min(growth_rate, 2.0))  # -50% ~ +200% 클램프
    elif len(annuals) == 1:
        latest_ni   = annuals[0].get("net_income")
        base_period = annuals[0].get("period", "")

    forward_eps = None
    forward_pe  = None
    if eps and eps > 0:
        rate = growth_rate if growth_rate is not None else 0.05  # 기본 5% 성장 가정
        forward_eps = round(eps * (1 + rate), 0)
        if current_price and forward_eps > 0:
            forward_pe = round(current_price / forward_eps, 2)

    return {
        "current_per":     per,
        "forward_eps":     forward_eps,
        "forward_pe":      forward_pe,
        "eps_growth_rate": round(growth_rate * 100, 1) if growth_rate is not None else None,
        "base_period":     base_period,       # 성장률 계산 기준 연도 (ex: "2025A")
        "data_note":       (
            "과거 실적 기반 추정 (애널리스트 컨센서스와 차이 있을 수 있음)"
            if growth_rate is not None else
            "성장률 데이터 부족 — 기본 5% 가정 적용"
        ),
    }


# ── 매수 타이밍 ───────────────────────────────────────────────────────────

def _calculate_timing(prices: list[float]) -> dict:
    if len(prices) < 20:
        return {"signal": "데이터 부족"}

    current  = prices[-1]
    rsi      = _rsi(prices)
    ma20     = _ma(prices, 20)
    ma60     = _ma(prices, 60)
    ma120    = _ma(prices, 120)
    bb_lo, bb_hi = _bollinger(prices, 20)

    # 52주 고가/저가
    window = prices[-min(len(prices), 252):]
    hi52   = max(window)
    lo52   = min(window)
    pct_from_lo = _safe_pct(current - lo52, lo52)
    pct_from_hi = _safe_pct(current - hi52, hi52)

    signals = []

    # RSI 기반 시그널
    if rsi is not None:
        if rsi < 25:
            signals.append(f"RSI {rsi:.1f} — 극심한 과매도 (강한 반등 기대)")
        elif rsi < 35:
            signals.append(f"RSI {rsi:.1f} — 과매도 구간 진입")
        elif rsi > 75:
            signals.append(f"RSI {rsi:.1f} — 과매수 (단기 조정 가능)")
        elif rsi > 65:
            signals.append(f"RSI {rsi:.1f} — 과매수 주의")

    # 이동평균 지지/저항
    if ma20 and abs(current - ma20) / ma20 < 0.03:
        signals.append(f"MA20({int(ma20):,}) 지지선 근접")
    if ma60 and abs(current - ma60) / ma60 < 0.03:
        signals.append(f"MA60({int(ma60):,}) 지지선 근접")
    if ma20 and ma60 and ma20 > ma60:
        signals.append("단기 이동평균 상승배열 (골든크로스)")
    if ma20 and ma60 and ma20 < ma60:
        signals.append("단기 이동평균 하락배열 (데드크로스)")

    # 볼린저밴드
    if bb_lo and current <= bb_lo * 1.02:
        signals.append(f"볼린저밴드 하단({int(bb_lo):,}) 근접 — 과매도 반등 가능")
    if bb_hi and current >= bb_hi * 0.98:
        signals.append(f"볼린저밴드 상단({int(bb_hi):,}) 근접 — 단기 저항")

    # 52주 저가 근접
    if pct_from_lo is not None and pct_from_lo < 10:
        signals.append(f"52주 저가 대비 +{pct_from_lo:.1f}% — 바닥권")

    # 종합 타이밍 판단
    if rsi is not None and rsi < 30 and (ma60 is None or current <= ma60 * 1.05):
        timing = "적극 분할매수"
    elif rsi is not None and rsi < 45:
        timing = "분할매수"
    elif rsi is not None and rsi > 70:
        timing = "고점 주의 — 신규 매수 자제"
    else:
        timing = "관망"

    return {
        "signal":        timing,
        "rsi":           rsi,
        "ma20":          round(ma20, 0) if ma20 else None,
        "ma60":          round(ma60, 0) if ma60 else None,
        "ma120":         round(ma120, 0) if ma120 else None,
        "bb_lower":      bb_lo,
        "bb_upper":      bb_hi,
        "support":       round(ma60, 0) if ma60 else round(lo52, 0),
        "resistance":    round(bb_hi, 0) if bb_hi else round(hi52 * 0.95, 0),
        "hi52":          round(hi52, 0),
        "lo52":          round(lo52, 0),
        "pct_from_lo52": pct_from_lo,
        "pct_from_hi52": pct_from_hi,
        "signals":       signals,
    }


# ── 거시환경 참고 ─────────────────────────────────────────────────────────

def _macro_context(macro: dict) -> list[str]:
    """거시지표 기반 투자 참고 메시지."""
    notes = []
    base_rate = macro.get("base_rate")
    usd_krw   = macro.get("usd_krw")
    cpi       = macro.get("cpi")

    if base_rate is not None:
        if base_rate >= 3.5:
            notes.append(f"기준금리 {base_rate}% — 고금리 환경, 성장주 밸류에이션 압박")
        elif base_rate <= 2.0:
            notes.append(f"기준금리 {base_rate}% — 저금리 환경, 주식 상대 매력 높음")
        else:
            notes.append(f"기준금리 {base_rate}%")

    if usd_krw is not None:
        if usd_krw >= 1400:
            notes.append(f"원/달러 {usd_krw:,.0f}원 — 고환율, 수출주 유리·수입 원가 압박")
        elif usd_krw <= 1200:
            notes.append(f"원/달러 {usd_krw:,.0f}원 — 저환율, 내수주 유리")
        else:
            notes.append(f"원/달러 {usd_krw:,.0f}원")

    return notes


# ── 종합 분석 ─────────────────────────────────────────────────────────────

def get_stock_analysis(ticker: str) -> dict:
    """종목 종합 분석 반환."""
    cache_key = f"analysis:{ticker}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    date        = latest_trading_date()
    from_ohlcv  = n_days_ago(365)
    from_trade  = n_days_ago(30)

    # 데이터 수집
    ohlcv      = get_stock_ohlcv(ticker, from_ohlcv, date)
    prices     = [r["c"] for r in ohlcv if r.get("c")]
    volumes    = [r["v"] for r in ohlcv if r.get("v") is not None]

    fund_series = get_stock_fundamental(ticker, from_ohlcv, date)
    fund        = fund_series[-1] if fund_series else {}

    financials  = get_financial_statements(ticker)
    trading     = get_investor_trading(ticker, from_trade, date)
    macro       = get_latest_macro()

    if not prices:
        return {"ticker": ticker, "error": "데이터 없음"}

    current_price = prices[-1]

    # 스코어링
    scoring = score_ticker(ticker, fund, prices, volumes, financials, trading)

    # 목표가
    target = _calculate_target_price(prices, fund, financials)

    # Forward P/E
    fwd_pe = _calculate_forward_pe(current_price, fund, financials)

    # 매수 타이밍
    timing = _calculate_timing(prices)

    # 공매도
    shorting = get_shorting_summary(ticker, days=20)

    # DART 공시
    disclosures = get_disclosures(ticker, days=90)

    # 거시환경
    macro_notes = _macro_context(macro)

    result = {
        "ticker":       ticker,
        "name":         get_ticker_name(ticker),
        "current_price": current_price,
        "scoring":      scoring,
        "target_price": target,
        "forward_pe":   fwd_pe,
        "timing":       timing,
        "shorting":     shorting,
        "disclosures":  disclosures[:10],
        "macro":        {**macro, "notes": macro_notes},
    }

    cache.set(cache_key, result, ttl=Config.CACHE_TTL_ANALYSIS)
    return result
