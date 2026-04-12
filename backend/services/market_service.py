"""시장 요약 및 KOSPI/KOSDAQ 지수 서비스."""
import logging
from pykrx import stock as krx_stock

from cache.ttl_cache import cache
from utils.date_utils import today_str, n_days_ago, fmt_datetime, latest_trading_date
from utils.serializers import ohlcv_df_to_chart
from config import Config
from services.stock_service import get_market_ohlcv_snapshot

logger = logging.getLogger(__name__)

KOSPI_INDEX_TICKER = "1001"
KOSDAQ_INDEX_TICKER = "2001"


def get_market_summary(market: str = "KOSPI") -> dict:
    cache_key = f"market_summary:{market}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    date = latest_trading_date()
    records = get_market_ohlcv_snapshot(date, market)

    if not records:
        return {"error": "데이터 없음", "date": date, "market": market}

    up = [r for r in records if (r.get("change_pct") or 0) > 0]
    down = [r for r in records if (r.get("change_pct") or 0) < 0]
    unchanged = [r for r in records if (r.get("change_pct") or 0) == 0]

    top_gainers = sorted(up, key=lambda x: x.get("change_pct") or 0, reverse=True)[:5]
    top_losers = sorted(down, key=lambda x: x.get("change_pct") or 0)[:5]
    top_volume = sorted(
        records, key=lambda x: x.get("trading_value") or 0, reverse=True
    )[:10]

    result = {
        "date": date,
        "market": market,
        "stats": {
            "total": len(records),
            "up": len(up),
            "down": len(down),
            "unchanged": len(unchanged),
        },
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "top_volume": top_volume,
    }
    cache.set(cache_key, result, ttl=Config.CACHE_TTL_MARKET)
    return result


def get_index_chart(market: str = "KOSPI", days: int = 90) -> list[dict]:
    """KOSPI/KOSDAQ 지수 OHLCV — pykrx 직접 조회 (지수 데이터는 DB에 미적재)."""
    ticker = KOSPI_INDEX_TICKER if market == "KOSPI" else KOSDAQ_INDEX_TICKER
    cache_key = f"index_chart:{market}:{days}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        to_date   = latest_trading_date()
        from_date = n_days_ago(days)
        df = krx_stock.get_index_ohlcv(from_date, to_date, ticker)
        if df.empty:
            return []
        df.index.name = "date"
        df.reset_index(inplace=True)
        df = df.iloc[:, :7]
        df.columns = ["date", "open", "high", "low", "close", "volume", "trading_value"]
        df["date"] = df["date"].apply(fmt_datetime)
        df["change_pct"] = df["close"].pct_change() * 100
        result = ohlcv_df_to_chart(df)
        cache.set(cache_key, result, ttl=Config.CACHE_TTL_MARKET)
        return result
    except Exception as exc:
        logger.error("지수 차트 조회 실패 (%s): %s", market, exc)
        return []
