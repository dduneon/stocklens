"""KRX 날짜 유틸리티."""
from datetime import datetime, timedelta


def today_str() -> str:
    """오늘 날짜를 YYYYMMDD 형식으로 반환."""
    return datetime.now().strftime("%Y%m%d")


def n_days_ago(n: int) -> str:
    """n일 전 날짜를 YYYYMMDD 형식으로 반환."""
    return (datetime.now() - timedelta(days=n)).strftime("%Y%m%d")


def to_display(date_str: str) -> str:
    """YYYYMMDD → YYYY-MM-DD."""
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str


def fmt_datetime(dt) -> str:
    """datetime 또는 Timestamp를 YYYY-MM-DD 문자열로 변환."""
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d")
    s = str(dt)
    return s[:10] if len(s) >= 10 else s


def latest_trading_date() -> str:
    """DB에서 가장 최근 거래일을 YYYYMMDD 형식으로 반환.
    DB가 비어있거나 연결 실패 시 오늘 날짜를 반환.
    """
    try:
        from db.repository import get_latest_available_date
        d = get_latest_available_date()
        if d:
            return d.replace("-", "")
    except Exception:
        pass
    return today_str()
