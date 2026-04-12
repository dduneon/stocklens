"""한국은행 ECOS API 거시경제 지표 수집 서비스.

수집 지표:
  - base_rate : 기준금리 (722Y001 / DD / 0101000)
  - usd_krw   : 원/달러 환율 (731Y004 / DD / 0000001)
  - cpi       : 소비자물가지수 (901Y009 / MM / 0)
"""
import logging
import requests
from datetime import datetime, timedelta

from config import Config
from cache.ttl_cache import cache
from utils.date_utils import n_days_ago, today_str

logger = logging.getLogger(__name__)

ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"

# 지표 정의: (stat_code, period_type, item_code, label)
# ECOS API cycle: 일별=D, 월별=M, 분기별=Q, 연별=A  (DD/MM 은 잘못된 값)
INDICATORS = {
    "base_rate": ("722Y001", "D", "0101000", "기준금리"),
    "usd_krw":   ("731Y001", "D", "0000001", "원/달러 환율"),   # 731Y001=외국환율 일별
    "cpi":       ("901Y009", "M", "0",       "소비자물가지수"),
}


def _ecos_fetch(stat_code: str, period_type: str, item_code: str,
                start: str, end: str) -> list[dict]:
    """ECOS StatisticSearch 호출. [{date, value}, ...] 반환."""
    if not Config.ECOS_API_KEY:
        return []
    url = (
        f"{ECOS_BASE}/{Config.ECOS_API_KEY}/json/kr"
        f"/1/1000/{stat_code}/{period_type}/{start}/{end}/{item_code}"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        rows = body.get("StatisticSearch", {}).get("row", [])
        result = []
        for r in rows:
            time_val = r.get("TIME", "")
            data_val = r.get("DATA_VALUE", "")
            if not time_val or not data_val:
                continue
            # DD: YYYYMMDD → YYYY-MM-DD / MM: YYYYMM → YYYY-MM-01
            if len(time_val) == 8:
                date_str = f"{time_val[:4]}-{time_val[4:6]}-{time_val[6:]}"
            elif len(time_val) == 6:
                date_str = f"{time_val[:4]}-{time_val[4:]}-01"
            else:
                continue
            try:
                result.append({"date": date_str, "value": float(data_val)})
            except ValueError:
                continue
        return result
    except Exception as e:
        logger.error("ECOS 조회 실패 (%s): %s", stat_code, e)
        return []


def get_macro_indicators(days: int = 365) -> dict:
    """전체 거시지표 최근 N일 반환.

    Returns:
        {
          "base_rate": [{"date": "2025-01-02", "value": 3.5}, ...],
          "usd_krw":   [...],
          "cpi":       [...],
          "latest":    {"base_rate": 3.5, "usd_krw": 1320.0, "cpi": 115.2}
        }
    """
    cache_key = f"macro_indicators:{days}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # D 형식은 YYYYMMDD, M 형식은 YYYYMM
    start_dd = n_days_ago(days)                    # YYYYMMDD
    end_dd   = today_str()
    start_mm = start_dd[:6]                        # YYYYMM
    end_mm   = end_dd[:6]

    result = {}
    latest = {}

    for key, (stat_code, period_type, item_code, _label) in INDICATORS.items():
        if period_type == "D":
            rows = _ecos_fetch(stat_code, period_type, item_code, start_dd, end_dd)
        else:
            rows = _ecos_fetch(stat_code, period_type, item_code, start_mm, end_mm)
        result[key] = rows
        latest[key] = rows[-1]["value"] if rows else None

    result["latest"] = latest
    cache.set(cache_key, result, ttl=Config.CACHE_TTL_MACRO)
    return result


def get_latest_macro() -> dict:
    """최신 거시지표 값만 반환 (스코어링·분석에 사용)."""
    data = get_macro_indicators(days=30)
    return data.get("latest", {})


def save_macro_to_db(days: int = 365) -> int:
    """ECOS 데이터를 DB에 저장. 배치 수집용."""
    from db.engine import get_session
    from db.models import MacroIndicator
    from sqlalchemy.dialects.mysql import insert as mysql_insert

    total = 0
    data = get_macro_indicators(days)

    rows = []
    for indicator, series in data.items():
        if indicator == "latest" or not isinstance(series, list):
            continue
        for item in series:
            rows.append({
                "indicator": indicator,
                "date": item["date"],
                "value": item["value"],
            })

    if rows:
        with get_session() as s:
            stmt = mysql_insert(MacroIndicator.__table__).values(rows)
            stmt = stmt.on_duplicate_key_update(value=stmt.inserted.value)
            result = s.execute(stmt)
            total = result.rowcount

    logger.info("macro_indicator upserted: %d rows", total)
    return total
