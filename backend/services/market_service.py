"""시장 요약 및 KOSPI/KOSDAQ 지수 서비스."""
import logging
from pykrx import stock as krx_stock

from cache.ttl_cache import cache
from utils.date_utils import today_str, n_days_ago, fmt_datetime, latest_trading_date
from utils.serializers import ohlcv_df_to_chart
from config import Config
from services.stock_service import get_market_ohlcv_snapshot
from krx_session.manager import login_krx, is_logged_in

logger = logging.getLogger(__name__)

KOSPI_INDEX_TICKER = "1001"
KOSDAQ_INDEX_TICKER = "2001"


def get_market_summary(market: str = "KOSPI") -> dict:
    date = latest_trading_date()
    cache_key = f"market_summary:{market}:{date}"   # 날짜 포함 → 배치 후 자동 갱신
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
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
    to_date   = latest_trading_date()
    from_date = n_days_ago(days)
    cache_key = f"index_chart:{market}:{days}:{to_date}"  # 날짜 포함 → 배치 후 자동 갱신
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # KRX 세션 만료 시 재로그인
    if not is_logged_in():
        logger.info("KRX 세션 만료 — 재로그인 시도")
        login_krx(Config.KRX_LOGIN_ID, Config.KRX_LOGIN_PW)

    try:
        df = krx_stock.get_index_ohlcv(from_date, to_date, ticker)
        if df.empty:
            # 세션 문제로 빈 DF 반환됐을 수 있음 — 재시도 1회
            logger.warning("지수 OHLCV 빈 응답 (%s) — 세션 갱신 후 재시도", market)
            login_krx(Config.KRX_LOGIN_ID, Config.KRX_LOGIN_PW)
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
