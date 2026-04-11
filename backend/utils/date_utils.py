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
