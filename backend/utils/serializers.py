"""pandas DataFrame → JSON-safe dict 변환 유틸리티."""
import math
import numpy as np
import pandas as pd
from typing import Any


def _safe_value(v: Any) -> Any:
    """numpy/pandas 타입을 JSON 직렬화 가능한 Python 기본 타입으로 변환."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(v, (pd.Timestamp,)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame을 JSON-safe 레코드 리스트로 변환."""
    records = []
    for row in df.to_dict(orient="records"):
        records.append({k: _safe_value(v) for k, v in row.items()})
    return records


def ohlcv_df_to_chart(df: pd.DataFrame, date_col: str = "date") -> list[dict]:
    """OHLCV DataFrame을 Chart.js candlestick 형식으로 변환.

    기대 컬럼: date, open, high, low, close, volume
    """
    result = []
    for row in df.to_dict(orient="records"):
        result.append({
            "x": _safe_value(row.get(date_col)),
            "o": _safe_value(row.get("open")),
            "h": _safe_value(row.get("high")),
            "l": _safe_value(row.get("low")),
            "c": _safe_value(row.get("close")),
            "v": _safe_value(row.get("volume")),
            "change_pct": _safe_value(row.get("change_pct")),
        })
    return result
