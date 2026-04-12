"""pykrx 공매도 데이터 수집 서비스.

KRX 로그인 세션(krx_session.manager)을 통해 pykrx API 정상 동작.
"""
import logging
import numpy as np
from pykrx import stock as krx_stock

from cache.ttl_cache import cache
from config import Config
from utils.date_utils import n_days_ago, latest_trading_date

SHORTING_UNAVAILABLE = False

logger = logging.getLogger(__name__)


def _pct_safe(num, den):
    if not num or not den or den == 0:
        return None
    return round(num / den * 100, 2)


# ── 종목별 공매도 ──────────────────────────────────────────────────────────

def get_shorting_data(ticker: str, from_date: str | None = None,
                      to_date: str | None = None) -> list[dict]:
    """종목 공매도 일별 데이터 반환.

    Returns: [{date, shorting_volume, total_volume, shorting_ratio, balance, balance_value}, ...]
    """
    from_date = from_date or n_days_ago(30)
    to_date   = to_date or latest_trading_date()

    cache_key = f"shorting:{ticker}:{from_date}:{to_date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # DB 우선
    rows = _get_shorting_from_db(ticker, from_date, to_date)
    if rows:
        cache.set(cache_key, rows, ttl=Config.CACHE_TTL_OHLCV)
        return rows

    # fallback: pykrx
    rows = _fetch_shorting_pykrx(ticker, from_date, to_date)
    cache.set(cache_key, rows, ttl=Config.CACHE_TTL_OHLCV)
    return rows


def _get_shorting_from_db(ticker: str, from_date: str, to_date: str) -> list[dict]:
    try:
        from db.engine import get_session
        from db.models import DailyShorting
        from sqlalchemy import select, and_
        from datetime import datetime

        fd = datetime.strptime(from_date, "%Y%m%d").date()
        td = datetime.strptime(to_date,   "%Y%m%d").date()

        with get_session() as s:
            q = (
                select(DailyShorting)
                .where(and_(
                    DailyShorting.ticker == ticker,
                    DailyShorting.date >= fd,
                    DailyShorting.date <= td,
                ))
                .order_by(DailyShorting.date)
            )
            result = []
            for r in s.execute(q).scalars().all():
                result.append({
                    "date":            str(r.date),
                    "shorting_volume": r.shorting_volume,
                    "total_volume":    r.total_volume,
                    "shorting_ratio":  float(r.shorting_ratio) if r.shorting_ratio else None,
                    "balance":         r.balance,
                    "balance_value":   r.balance_value,
                })
            return result
    except Exception as e:
        logger.debug("공매도 DB 조회 실패: %s", e)
        return []


def _fetch_shorting_pykrx(ticker: str, from_date: str, to_date: str) -> list[dict]:
    """pykrx로 공매도 데이터 수집 시도. KRX API 변경으로 현재 수집 불가."""
    if SHORTING_UNAVAILABLE:
        return []

    result = {}
    try:
        vol_df = krx_stock.get_shorting_volume_by_date(from_date, to_date, ticker)
        if not vol_df.empty:
            vol_df.index.name = "date"
            vol_df.reset_index(inplace=True)
            for _, row in vol_df.iterrows():
                d = str(row["date"])[:10]
                result[d] = {
                    "date":            d,
                    "shorting_volume": int(row.get("공매도", 0) or 0),
                    "total_volume":    int(row.get("매수", 0) or 0),
                    "shorting_ratio":  float(row.get("비중", 0) or 0),
                    "balance":         None,
                    "balance_value":   None,
                }
    except Exception as e:
        logger.debug("공매도 거래량 조회 실패 (%s): %s", ticker, e)

    try:
        bal_df = krx_stock.get_shorting_balance_by_date(from_date, to_date, ticker)
        if not bal_df.empty:
            bal_df.index.name = "date"
            bal_df.reset_index(inplace=True)
            for _, row in bal_df.iterrows():
                d = str(row["date"])[:10]
                if d in result:
                    result[d]["balance"]       = int(row.get("공매도잔고", 0) or 0)
                    result[d]["balance_value"] = int(row.get("공매도금액", 0) or 0)
    except Exception as e:
        logger.debug("공매도 잔고 조회 실패 (%s): %s", ticker, e)

    return sorted(result.values(), key=lambda x: x["date"])


def get_shorting_summary(ticker: str, days: int = 20) -> dict:
    """최근 N 거래일 공매도 요약 (분석용)."""
    rows = get_shorting_data(ticker, n_days_ago(days * 2), latest_trading_date())
    rows = rows[-days:] if len(rows) > days else rows
    if not rows:
        return {}

    ratios = [r["shorting_ratio"] for r in rows if r.get("shorting_ratio") is not None]
    avg_ratio   = round(float(np.mean(ratios)), 2) if ratios else None
    latest_ratio = ratios[-1] if ratios else None
    trend = None
    if len(ratios) >= 5:
        recent  = float(np.mean(ratios[-5:]))
        earlier = float(np.mean(ratios[:5]))
        if recent > earlier * 1.2:
            trend = "급증"
        elif recent > earlier * 1.05:
            trend = "증가"
        elif recent < earlier * 0.8:
            trend = "급감"
        elif recent < earlier * 0.95:
            trend = "감소"
        else:
            trend = "보합"

    return {
        "avg_ratio":    avg_ratio,
        "latest_ratio": latest_ratio,
        "trend":        trend,
        "series":       rows,
    }


# ── 시장 공매도 랭킹 ──────────────────────────────────────────────────────

def get_market_shorting_ranking(market: str = "KOSPI", top_n: int = 20) -> dict:
    """시장 전체 공매도 비율 상위 종목 반환.

    Returns:
        {"available": bool, "reason": str|None, "data": [...]}
    """
    if SHORTING_UNAVAILABLE:
        return {
            "available": False,
            "reason": "KRX 공매도 API 구조 변경으로 수집 불가 (pykrx 업데이트 대기 중)",
            "data": [],
        }

    date = latest_trading_date()
    cache_key = f"shorting_ranking:{market}:{date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        df = krx_stock.get_shorting_volume_by_ticker(date, market=market)
        if df is None or df.empty:
            return {"available": True, "reason": None, "data": []}

        df.index.name = "ticker"
        df.reset_index(inplace=True)

        from services.stock_service import get_ticker_name
        rows = []
        for _, row in df.iterrows():
            ticker = str(row.get("ticker", ""))
            ratio = float(row.get("비중", 0) or 0)
            rows.append({
                "ticker": ticker,
                "name": get_ticker_name(ticker),
                "shorting_volume": int(row.get("공매도", 0) or 0),
                "total_volume":    int(row.get("매수", 0) or 0),
                "shorting_ratio":  ratio,
            })

        rows = sorted(rows, key=lambda x: x["shorting_ratio"], reverse=True)[:top_n]
        result = {"available": True, "reason": None, "data": rows}
        cache.set(cache_key, result, ttl=Config.CACHE_TTL_MARKET)
        return result
    except Exception as e:
        logger.error("시장 공매도 랭킹 조회 실패: %s", e)
        return {"available": False, "reason": str(e), "data": []}


# ── DB 저장 (배치용) ──────────────────────────────────────────────────────

def save_shorting_to_db(ticker: str, from_date: str, to_date: str) -> int:
    rows = _fetch_shorting_pykrx(ticker, from_date, to_date)
    if not rows:
        return 0
    from db.engine import get_session
    from db.models import DailyShorting
    from sqlalchemy.dialects.mysql import insert as mysql_insert
    from datetime import datetime

    db_rows = []
    for r in rows:
        db_rows.append({
            "ticker":          ticker,
            "date":            datetime.strptime(r["date"], "%Y-%m-%d").date(),
            "shorting_volume": r.get("shorting_volume"),
            "total_volume":    r.get("total_volume"),
            "shorting_ratio":  r.get("shorting_ratio"),
            "balance":         r.get("balance"),
            "balance_value":   r.get("balance_value"),
        })

    with get_session() as s:
        stmt = mysql_insert(DailyShorting.__table__).values(db_rows)
        update_cols = {
            c.name: stmt.inserted[c.name]
            for c in DailyShorting.__table__.columns
            if c.name not in ("ticker", "date")
        }
        stmt = stmt.on_duplicate_key_update(**update_cols)
        result = s.execute(stmt)
    return result.rowcount
