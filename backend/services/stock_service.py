"""개별 종목 및 전체 시장 OHLCV/펀더멘털 데이터 서비스."""
import logging
import pandas as pd
from pykrx import stock
from cache.ttl_cache import cache
from utils.date_utils import today_str, n_days_ago, fmt_datetime
from utils.serializers import df_to_records, ohlcv_df_to_chart
from config import Config

logger = logging.getLogger(__name__)


# ── 종목 목록 ──────────────────────────────────────────────────────────────

def get_ticker_list(market: str = "KOSPI") -> list[dict]:
    cache_key = f"ticker_list:{market}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        tickers = stock.get_market_ticker_list(market=market)
        result = []
        for t in tickers:
            try:
                name = stock.get_market_ticker_name(t)
            except Exception:
                name = ""
            result.append({"ticker": t, "name": name})
        cache.set(cache_key, result, ttl=Config.CACHE_TTL_FUNDAMENTAL)
        return result
    except Exception as exc:
        logger.error("종목 목록 조회 실패: %s", exc)
        return []


# ── 시장 전체 OHLCV (단일 날짜) ───────────────────────────────────────────

def get_market_ohlcv_snapshot(date: str | None = None, market: str = "KOSPI") -> list[dict]:
    """특정 날짜의 전체 시장 OHLCV 반환."""
    date = date or today_str()
    cache_key = f"market_ohlcv:{market}:{date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        df = stock.get_market_ohlcv(date, market=market)
        if df.empty:
            return []
        df.index.name = "ticker"
        df.reset_index(inplace=True)
        df.columns = ["ticker", "open", "high", "low", "close",
                      "volume", "trading_value", "change_pct"]
        records = df_to_records(df)
        cache.set(cache_key, records, ttl=Config.CACHE_TTL_MARKET)
        return records
    except Exception as exc:
        logger.error("시장 OHLCV 조회 실패 (%s %s): %s", market, date, exc)
        return []


# ── 개별 종목 OHLCV (기간) ────────────────────────────────────────────────

def get_stock_ohlcv(
    ticker: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    from_date = from_date or n_days_ago(365)
    to_date = to_date or today_str()
    cache_key = f"stock_ohlcv:{ticker}:{from_date}:{to_date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        df = stock.get_market_ohlcv(from_date, to_date, ticker)
        if df.empty:
            return []
        df.index.name = "date"
        df.reset_index(inplace=True)
        df.columns = ["date", "open", "high", "low", "close",
                      "volume", "trading_value", "change_pct"]
        df["date"] = df["date"].apply(fmt_datetime)
        records = ohlcv_df_to_chart(df)
        cache.set(cache_key, records, ttl=Config.CACHE_TTL_OHLCV)
        return records
    except Exception as exc:
        logger.error("종목 OHLCV 조회 실패 (%s): %s", ticker, exc)
        return []


# ── 시장 전체 펀더멘털 (단일 날짜) ────────────────────────────────────────

def get_market_fundamental_snapshot(date: str | None = None, market: str = "ALL") -> list[dict]:
    date = date or today_str()
    cache_key = f"market_fundamental:{market}:{date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        df = stock.get_market_fundamental(date, market=market)
        if df.empty:
            return []
        df.index.name = "ticker"
        df.reset_index(inplace=True)
        # 컬럼: ticker, BPS, PER, PBR, EPS, DIV, DPS
        df.columns = [c.lower() if c != "ticker" else c for c in df.columns]
        records = df_to_records(df)
        cache.set(cache_key, records, ttl=Config.CACHE_TTL_FUNDAMENTAL)
        return records
    except Exception as exc:
        logger.error("시장 펀더멘털 조회 실패 (%s %s): %s", market, date, exc)
        return []


# ── 개별 종목 펀더멘털 (기간) ─────────────────────────────────────────────

def get_stock_fundamental(
    ticker: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    from_date = from_date or n_days_ago(365)
    to_date = to_date or today_str()
    cache_key = f"stock_fundamental:{ticker}:{from_date}:{to_date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        df = stock.get_market_fundamental(from_date, to_date, ticker)
        if df.empty:
            return []
        df.index.name = "date"
        df.reset_index(inplace=True)
        df["date"] = df["date"].apply(fmt_datetime)
        df.columns = [c.lower() if c != "date" else c for c in df.columns]
        records = df_to_records(df)
        cache.set(cache_key, records, ttl=Config.CACHE_TTL_FUNDAMENTAL)
        return records
    except Exception as exc:
        logger.error("종목 펀더멘털 조회 실패 (%s): %s", ticker, exc)
        return []


# ── 시가총액 ──────────────────────────────────────────────────────────────

def get_market_cap_snapshot(date: str | None = None, market: str = "KOSPI") -> list[dict]:
    date = date or today_str()
    cache_key = f"market_cap:{market}:{date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        df = stock.get_market_cap(date, market=market)
        if df.empty:
            return []
        df.index.name = "ticker"
        df.reset_index(inplace=True)
        df.columns = ["ticker", "market_cap", "volume", "trading_value", "listed_shares"]
        records = df_to_records(df)
        cache.set(cache_key, records, ttl=Config.CACHE_TTL_MARKET)
        return records
    except Exception as exc:
        logger.error("시가총액 조회 실패 (%s %s): %s", market, date, exc)
        return []


def get_ticker_name(ticker: str) -> str:
    try:
        return stock.get_market_ticker_name(ticker)
    except Exception:
        return ""
