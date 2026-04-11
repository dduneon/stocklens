"""DB 읽기 레포지토리. 서비스 레이어에서 호출합니다."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, and_, desc, text
from db.engine import get_session
from db.models import (
    Ticker, DailyOHLCV, DailyFundamental, DailyMarketCap,
    DailyInvestorTrading, FinancialStatement,
)

logger = logging.getLogger(__name__)


# ── 유틸 ──────────────────────────────────────────────────────────────────

def _model_to_dict(obj) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _date_from(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


# ── Tickers ───────────────────────────────────────────────────────────────

def get_ticker_list(market: str | None = None) -> list[dict]:
    with get_session() as s:
        q = select(Ticker)
        if market:
            q = q.where(Ticker.market == market)
        q = q.order_by(Ticker.ticker)
        rows = s.execute(q).scalars().all()
        return [_model_to_dict(r) for r in rows]


def get_ticker(ticker: str) -> dict | None:
    with get_session() as s:
        row = s.get(Ticker, ticker)
        return _model_to_dict(row) if row else None


# ── OHLCV ─────────────────────────────────────────────────────────────────

def get_latest_ohlcv_date() -> date | None:
    with get_session() as s:
        result = s.execute(text("SELECT MAX(date) FROM daily_ohlcv")).scalar()
        return result


def get_market_ohlcv_snapshot(target_date: str, market: str = "KOSPI") -> list[dict]:
    d = _date_from(target_date)
    with get_session() as s:
        q = (
            select(DailyOHLCV, Ticker.name, Ticker.market)
            .join(Ticker, Ticker.ticker == DailyOHLCV.ticker)
            .where(
                and_(
                    DailyOHLCV.date == d,
                    Ticker.market == market,
                )
            )
        )
        rows = s.execute(q).all()
        result = []
        for ohlcv, name, mkt in rows:
            d_ = _model_to_dict(ohlcv)
            d_["name"] = name
            d_["date"] = str(d_["date"])
            result.append(d_)
        return result


def get_stock_ohlcv(ticker: str, from_date: str, to_date: str) -> list[dict]:
    fd = _date_from(from_date)
    td = _date_from(to_date)
    with get_session() as s:
        q = (
            select(DailyOHLCV)
            .where(
                and_(
                    DailyOHLCV.ticker == ticker,
                    DailyOHLCV.date >= fd,
                    DailyOHLCV.date <= td,
                )
            )
            .order_by(DailyOHLCV.date)
        )
        rows = s.execute(q).scalars().all()
        result = []
        for r in rows:
            d = _model_to_dict(r)
            # Chart.js candlestick 형식으로 변환
            result.append({
                "x": str(d["date"]),
                "o": d["open"],
                "h": d["high"],
                "l": d["low"],
                "c": d["close"],
                "v": d["volume"],
                "change_pct": float(d["change_pct"]) if d["change_pct"] is not None else None,
            })
        return result


# ── Fundamentals ──────────────────────────────────────────────────────────

def get_market_fundamental_snapshot(target_date: str, market: str = "ALL") -> list[dict]:
    d = _date_from(target_date)
    with get_session() as s:
        q = select(DailyFundamental, Ticker.market).join(
            Ticker, Ticker.ticker == DailyFundamental.ticker
        ).where(DailyFundamental.date == d)
        if market != "ALL":
            q = q.where(Ticker.market == market)
        rows = s.execute(q).all()
        result = []
        for fund, _ in rows:
            d_ = _model_to_dict(fund)
            d_["date"] = str(d_["date"])
            for k in ("per", "pbr", "div"):
                if d_[k] is not None:
                    d_[k] = float(d_[k])
            result.append(d_)
        return result


def get_stock_fundamental(ticker: str, from_date: str, to_date: str) -> list[dict]:
    fd = _date_from(from_date)
    td = _date_from(to_date)
    with get_session() as s:
        q = (
            select(DailyFundamental)
            .where(
                and_(
                    DailyFundamental.ticker == ticker,
                    DailyFundamental.date >= fd,
                    DailyFundamental.date <= td,
                )
            )
            .order_by(DailyFundamental.date)
        )
        rows = s.execute(q).scalars().all()
        result = []
        for r in rows:
            d = _model_to_dict(r)
            d["date"] = str(d["date"])
            for k in ("per", "pbr", "div"):
                if d[k] is not None:
                    d[k] = float(d[k])
            result.append(d)
        return result


# ── Market Cap ────────────────────────────────────────────────────────────

def get_market_cap_snapshot(target_date: str, market: str = "KOSPI") -> list[dict]:
    d = _date_from(target_date)
    with get_session() as s:
        q = (
            select(DailyMarketCap, Ticker.market)
            .join(Ticker, Ticker.ticker == DailyMarketCap.ticker)
            .where(
                and_(
                    DailyMarketCap.date == d,
                    Ticker.market == market,
                )
            )
        )
        rows = s.execute(q).all()
        result = []
        for cap, _ in rows:
            d_ = _model_to_dict(cap)
            d_["date"] = str(d_["date"])
            result.append(d_)
        return result


# ── Investor Trading ──────────────────────────────────────────────────────

def get_investor_trading(ticker: str, from_date: str, to_date: str) -> list[dict]:
    fd = _date_from(from_date)
    td = _date_from(to_date)
    with get_session() as s:
        q = (
            select(DailyInvestorTrading)
            .where(
                and_(
                    DailyInvestorTrading.ticker == ticker,
                    DailyInvestorTrading.date >= fd,
                    DailyInvestorTrading.date <= td,
                )
            )
            .order_by(DailyInvestorTrading.date)
        )
        rows = s.execute(q).scalars().all()
        result = []
        for r in rows:
            d = _model_to_dict(r)
            d["date"] = str(d["date"])
            d["individual_net"] = (d.get("individual_buy") or 0) - (d.get("individual_sell") or 0)
            d["institutional_net"] = (d.get("institutional_buy") or 0) - (d.get("institutional_sell") or 0)
            d["foreign_net"] = (d.get("foreign_buy") or 0) - (d.get("foreign_sell") or 0)
            result.append(d)
        return result


def get_market_investor_snapshot(target_date: str, market: str = "KOSPI") -> list[dict]:
    d = _date_from(target_date)
    with get_session() as s:
        q = (
            select(DailyInvestorTrading, Ticker.market)
            .join(Ticker, Ticker.ticker == DailyInvestorTrading.ticker)
            .where(
                and_(
                    DailyInvestorTrading.date == d,
                    Ticker.market == market,
                )
            )
        )
        rows = s.execute(q).all()
        result = []
        for inv, _ in rows:
            d_ = _model_to_dict(inv)
            d_["date"] = str(d_["date"])
            d_["individual_net"] = (d_.get("individual_buy") or 0) - (d_.get("individual_sell") or 0)
            d_["institutional_net"] = (d_.get("institutional_buy") or 0) - (d_.get("institutional_sell") or 0)
            d_["foreign_net"] = (d_.get("foreign_buy") or 0) - (d_.get("foreign_sell") or 0)
            result.append(d_)
        return result


# ── Financial Statements ──────────────────────────────────────────────────

def get_financial_statements(ticker: str) -> list[dict]:
    with get_session() as s:
        q = (
            select(FinancialStatement)
            .where(FinancialStatement.ticker == ticker)
            .order_by(desc(FinancialStatement.period))
        )
        rows = s.execute(q).scalars().all()
        result = []
        for r in rows:
            d = _model_to_dict(r)
            d.pop("updated_at", None)
            result.append(d)
        return result


# ── 최신 거래일 조회 (fallback용) ─────────────────────────────────────────

def get_latest_available_date(market: str = "KOSPI") -> str | None:
    with get_session() as s:
        q = (
            select(DailyOHLCV.date)
            .join(Ticker, Ticker.ticker == DailyOHLCV.ticker)
            .where(Ticker.market == market)
            .order_by(desc(DailyOHLCV.date))
            .limit(1)
        )
        result = s.execute(q).scalar()
        return str(result) if result else None
