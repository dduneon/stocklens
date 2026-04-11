"""개별 종목 및 전체 시장 데이터 서비스.

DB에 데이터가 있으면 DB에서 반환 (< 100ms),
없으면 pykrx에서 온디맨드로 조회합니다 (fallback).
"""
import logging
from pykrx import stock as krx_stock

from cache.ttl_cache import cache
from utils.date_utils import today_str, n_days_ago, fmt_datetime
from utils.serializers import df_to_records, ohlcv_df_to_chart
from config import Config
import db.repository as repo

logger = logging.getLogger(__name__)


# ── 종목 목록 ──────────────────────────────────────────────────────────────

def get_ticker_list(market: str = "KOSPI") -> list[dict]:
    cache_key = f"ticker_list:{market}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # DB 우선
    rows = repo.get_ticker_list(market)
    if rows:
        cache.set(cache_key, rows, ttl=Config.CACHE_TTL_FUNDAMENTAL)
        return rows

    # fallback: pykrx
    try:
        tickers = krx_stock.get_market_ticker_list(market=market)
        result = [{"ticker": t, "name": _ticker_name(t), "market": market} for t in tickers]
        cache.set(cache_key, result, ttl=Config.CACHE_TTL_FUNDAMENTAL)
        return result
    except Exception as exc:
        logger.error("종목 목록 조회 실패: %s", exc)
        return []


def get_ticker_name(ticker: str) -> str:
    t = repo.get_ticker(ticker)
    if t:
        return t.get("name", "")
    try:
        return krx_stock.get_market_ticker_name(ticker)
    except Exception:
        return ""


def _ticker_name(ticker: str) -> str:
    try:
        return krx_stock.get_market_ticker_name(ticker)
    except Exception:
        return ""


# ── 시장 전체 OHLCV 스냅샷 ────────────────────────────────────────────────

def get_market_ohlcv_snapshot(date: str | None = None, market: str = "KOSPI") -> list[dict]:
    date = date or today_str()
    cache_key = f"market_ohlcv:{market}:{date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # DB 우선
    rows = repo.get_market_ohlcv_snapshot(date, market)
    if rows:
        cache.set(cache_key, rows, ttl=Config.CACHE_TTL_MARKET)
        return rows

    # fallback: 가장 최신 날짜로 재시도
    latest = repo.get_latest_available_date(market)
    if latest and latest != date:
        logger.info("요청 날짜 %s에 데이터 없음, 최신 날짜 %s 사용", date, latest)
        rows = repo.get_market_ohlcv_snapshot(latest, market)
        if rows:
            cache.set(cache_key, rows, ttl=Config.CACHE_TTL_MARKET)
            return rows

    # fallback: pykrx
    try:
        import pandas as pd
        df = krx_stock.get_market_ohlcv(date, market=market)
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


# ── 개별 종목 OHLCV ────────────────────────────────────────────────────────

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

    # DB 우선
    rows = repo.get_stock_ohlcv(ticker, from_date, to_date)
    if rows:
        cache.set(cache_key, rows, ttl=Config.CACHE_TTL_OHLCV)
        return rows

    # fallback: pykrx
    try:
        df = krx_stock.get_market_ohlcv(from_date, to_date, ticker)
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


# ── 시장 전체 펀더멘털 스냅샷 ─────────────────────────────────────────────

def get_market_fundamental_snapshot(date: str | None = None, market: str = "ALL") -> list[dict]:
    date = date or today_str()
    cache_key = f"market_fundamental:{market}:{date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # DB 우선
    rows = repo.get_market_fundamental_snapshot(date, market)
    if rows:
        cache.set(cache_key, rows, ttl=Config.CACHE_TTL_FUNDAMENTAL)
        return rows

    # fallback: pykrx
    try:
        df = krx_stock.get_market_fundamental(date, market=market)
        if df.empty:
            return []
        df.index.name = "ticker"
        df.reset_index(inplace=True)
        df.columns = [c.lower() if c != "ticker" else c for c in df.columns]
        records = df_to_records(df)
        cache.set(cache_key, records, ttl=Config.CACHE_TTL_FUNDAMENTAL)
        return records
    except Exception as exc:
        logger.error("시장 펀더멘털 조회 실패 (%s %s): %s", market, date, exc)
        return []


# ── 개별 종목 펀더멘털 ─────────────────────────────────────────────────────

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

    # DB 우선
    rows = repo.get_stock_fundamental(ticker, from_date, to_date)
    if rows:
        cache.set(cache_key, rows, ttl=Config.CACHE_TTL_FUNDAMENTAL)
        return rows

    # fallback: pykrx
    try:
        df = krx_stock.get_market_fundamental(from_date, to_date, ticker)
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


# ── 시가총액 스냅샷 ───────────────────────────────────────────────────────

def get_market_cap_snapshot(date: str | None = None, market: str = "KOSPI") -> list[dict]:
    date = date or today_str()
    cache_key = f"market_cap:{market}:{date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # DB 우선
    rows = repo.get_market_cap_snapshot(date, market)
    if rows:
        cache.set(cache_key, rows, ttl=Config.CACHE_TTL_MARKET)
        return rows

    # fallback: pykrx
    try:
        df = krx_stock.get_market_cap(date, market=market)
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


# ── 투자자별 매매동향 ──────────────────────────────────────────────────────

def get_investor_trading(
    ticker: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    from_date = from_date or n_days_ago(30)
    to_date = to_date or today_str()
    cache_key = f"investor_trading:{ticker}:{from_date}:{to_date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # DB 우선
    rows = repo.get_investor_trading(ticker, from_date, to_date)
    if rows:
        cache.set(cache_key, rows, ttl=Config.CACHE_TTL_MARKET)
        return rows

    # fallback: pykrx
    try:
        df = krx_stock.get_market_trading_value_by_investor(from_date, to_date, ticker)
        if df.empty:
            return []
        df.index.name = "date"
        df.reset_index(inplace=True)
        df["date"] = df["date"].apply(fmt_datetime)
        records = df_to_records(df)
        cache.set(cache_key, records, ttl=Config.CACHE_TTL_MARKET)
        return records
    except Exception as exc:
        logger.error("투자자 수급 조회 실패 (%s): %s", ticker, exc)
        return []


# ── 재무제표 ──────────────────────────────────────────────────────────────

def get_financial_statements(ticker: str) -> list[dict]:
    cache_key = f"financials:{ticker}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    rows = repo.get_financial_statements(ticker)
    cache.set(cache_key, rows, ttl=Config.CACHE_TTL_FUNDAMENTAL)
    return rows
