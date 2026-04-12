from flask import Blueprint, jsonify, request
from services.stock_service import (
    get_ticker_list,
    get_market_ohlcv_snapshot,
    get_market_fundamental_snapshot,
    get_market_cap_snapshot,
    get_stock_ohlcv,
    get_stock_fundamental,
    get_ticker_name,
    get_investor_trading,
    get_financial_statements,
)
from services.investor_service import (
    get_stock_investor_flow,
    get_stock_investor_summary,
)
from utils.date_utils import today_str, n_days_ago, latest_trading_date

stocks_bp = Blueprint("stocks", __name__)


@stocks_bp.get("/")
def list_stocks():
    market = request.args.get("market", "KOSPI")
    date = request.args.get("date", latest_trading_date())
    search = request.args.get("search", "").strip().lower()

    # OHLCV + 시가총액 + 펀더멘털 병합
    ohlcv_list = get_market_ohlcv_snapshot(date, market)
    cap_list = get_market_cap_snapshot(date, market)
    fund_list = get_market_fundamental_snapshot(date)

    cap_map = {r["ticker"]: r for r in cap_list}
    fund_map = {r["ticker"]: r for r in fund_list}
    ticker_names = {r["ticker"]: r["name"] for r in get_ticker_list(market)}

    results = []
    for row in ohlcv_list:
        ticker = row.get("ticker", "")
        name = ticker_names.get(ticker, "")
        if search and search not in ticker.lower() and search not in name.lower():
            continue
        fund = fund_map.get(ticker, {})
        cap = cap_map.get(ticker, {})
        results.append({
            "ticker": ticker,
            "name": name,
            "close": row.get("close"),
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "volume": row.get("volume"),
            "trading_value": row.get("trading_value"),
            "change_pct": row.get("change_pct"),
            "market_cap": cap.get("market_cap"),
            "per": fund.get("per"),
            "pbr": fund.get("pbr"),
            "div": fund.get("div"),
        })

    # 시가총액 내림차순
    results.sort(key=lambda x: x.get("market_cap") or 0, reverse=True)

    page = int(request.args.get("page", 1))
    per_page = min(int(request.args.get("per_page", 50)), 200)
    start = (page - 1) * per_page
    paginated = results[start: start + per_page]

    return jsonify({
        "market": market,
        "date": date,
        "total": len(results),
        "page": page,
        "per_page": per_page,
        "stocks": paginated,
    })


@stocks_bp.get("/<ticker>")
def stock_detail(ticker: str):
    name = get_ticker_name(ticker)
    date = latest_trading_date()
    from_date = n_days_ago(365)

    ohlcv = get_stock_ohlcv(ticker, from_date, date)
    fundamentals = get_stock_fundamental(ticker, from_date, date)
    latest_fund = fundamentals[-1] if fundamentals else {}

    prices = [r["c"] for r in ohlcv if r.get("c")]
    latest_price = prices[-1] if prices else None
    prev_price = prices[-2] if len(prices) >= 2 else None
    change = round(latest_price - prev_price, 2) if latest_price and prev_price else None
    change_pct = round((change / prev_price) * 100, 2) if change and prev_price else None

    return jsonify({
        "ticker": ticker,
        "name": name,
        "close": latest_price,
        "change": change,
        "change_pct": change_pct,
        "fundamentals": latest_fund,
        "ohlcv_count": len(ohlcv),
    })


@stocks_bp.get("/<ticker>/ohlcv")
def stock_ohlcv(ticker: str):
    days = min(int(request.args.get("days", 365)), 730)
    from_date = request.args.get("from_date", n_days_ago(days))
    to_date = request.args.get("to_date", today_str())
    data = get_stock_ohlcv(ticker, from_date, to_date)
    return jsonify({
        "ticker": ticker,
        "from": from_date,
        "to": to_date,
        "data": data,
    })


@stocks_bp.get("/<ticker>/fundamentals")
def stock_fundamentals(ticker: str):
    days = min(int(request.args.get("days", 365)), 730)
    from_date = request.args.get("from_date", n_days_ago(days))
    to_date = request.args.get("to_date", today_str())
    data = get_stock_fundamental(ticker, from_date, to_date)
    return jsonify({
        "ticker": ticker,
        "from": from_date,
        "to": to_date,
        "data": data,
    })


@stocks_bp.get("/<ticker>/investor-trading")
def stock_investor_trading(ticker: str):
    """종목별 투자자 수급: 일별 순매수 추이(flow) + 기간 합산(summary)."""
    days = min(int(request.args.get("days", 60)), 365)
    from_date = request.args.get("from_date", n_days_ago(days))
    to_date = request.args.get("to_date", today_str())
    flow    = get_stock_investor_flow(ticker, from_date, to_date)
    summary = get_stock_investor_summary(ticker, from_date, to_date)
    return jsonify({
        "ticker":   ticker,
        "from":     from_date,
        "to":       to_date,
        "flow":     flow,
        "summary":  summary,
    })


@stocks_bp.get("/<ticker>/financials")
def stock_financials(ticker: str):
    data = get_financial_statements(ticker)
    return jsonify({
        "ticker": ticker,
        "data": data,
    })
