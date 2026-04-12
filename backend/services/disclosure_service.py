"""DART 공시 수집 서비스.

주요 공시 유형:
  A: 정기공시 (사업보고서, 반기보고서 등)
  B: 주요사항보고 (유상증자, 자기주식 등)
  C: 발행공시
  D: 지분공시 (대량보유, 임원 지분 변동)
  F: 외부감사 관련
"""
import logging
import requests
from datetime import datetime

from config import Config
from cache.ttl_cache import cache
from utils.date_utils import n_days_ago, today_str

logger = logging.getLogger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"

# 투자자에게 중요한 공시 유형
IMPORTANT_TYPES = {"A", "B", "D", "F"}

CATEGORY_LABEL = {
    "A": "정기공시",
    "B": "주요사항",
    "C": "발행공시",
    "D": "지분공시",
    "E": "기타공시",
    "F": "외부감사",
    "G": "펀드공시",
    "H": "자산유동화",
    "I": "거래소공시",
    "J": "공정위공시",
}


def _get_corp_code(ticker: str) -> str | None:
    """ticker → DART 고유번호 (corp_code) 변환."""
    cache_key = f"corp_code:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # DART 기업코드 ZIP 파일에서 매핑 (DartClient 재활용)
    try:
        import zipfile, io, xml.etree.ElementTree as ET
        url = f"{DART_BASE}/corpCode.xml"
        resp = requests.get(url, params={"crtfc_key": Config.DART_API_KEY}, timeout=30)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            with zf.open(zf.namelist()[0]) as f:
                tree = ET.parse(f)
                for corp in tree.getroot().findall("list"):
                    stock_code = corp.findtext("stock_code", "").strip()
                    corp_code  = corp.findtext("corp_code",  "").strip()
                    if stock_code == ticker:
                        cache.set(cache_key, corp_code, ttl=86400)
                        return corp_code
    except Exception as e:
        logger.debug("DART corp_code 조회 실패 (%s): %s", ticker, e)
    return None


# 전체 매핑을 한 번만 로드하는 캐시
_CORP_MAP: dict[str, str] = {}

def _get_corp_map() -> dict[str, str]:
    global _CORP_MAP
    if _CORP_MAP:
        return _CORP_MAP
    try:
        import zipfile, io, xml.etree.ElementTree as ET
        url = f"{DART_BASE}/corpCode.xml"
        resp = requests.get(url, params={"crtfc_key": Config.DART_API_KEY}, timeout=30)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            with zf.open(zf.namelist()[0]) as f:
                tree = ET.parse(f)
                for corp in tree.getroot().findall("list"):
                    sc = corp.findtext("stock_code", "").strip()
                    cc = corp.findtext("corp_code",  "").strip()
                    if sc:
                        _CORP_MAP[sc] = cc
        logger.info("DART 기업코드 매핑 로드: %d건", len(_CORP_MAP))
    except Exception as e:
        logger.error("DART 기업코드 로드 실패: %s", e)
    return _CORP_MAP


def get_disclosures(ticker: str, days: int = 90) -> list[dict]:
    """종목 최근 공시 목록 반환.

    Returns: [{rcept_no, disclosed_at, title, category, category_label, url}, ...]
    """
    cache_key = f"disclosures:{ticker}:{days}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # DB 우선
    rows = _get_disclosures_from_db(ticker, days)
    if rows:
        cache.set(cache_key, rows, ttl=Config.CACHE_TTL_MACRO)
        return rows

    # fallback: DART API 직접 호출
    rows = _fetch_disclosures_dart(ticker, days)
    cache.set(cache_key, rows, ttl=Config.CACHE_TTL_MACRO)
    return rows


def _get_disclosures_from_db(ticker: str, days: int) -> list[dict]:
    try:
        from db.engine import get_session
        from db.models import DartDisclosure
        from sqlalchemy import select, and_
        from datetime import date, timedelta

        cutoff = (datetime.today() - timedelta(days=days)).date()
        with get_session() as s:
            q = (
                select(DartDisclosure)
                .where(and_(
                    DartDisclosure.ticker == ticker,
                    DartDisclosure.disclosed_at >= cutoff,
                ))
                .order_by(DartDisclosure.disclosed_at.desc())
                .limit(30)
            )
            result = []
            for r in s.execute(q).scalars().all():
                result.append({
                    "rcept_no":       r.rcept_no,
                    "disclosed_at":   str(r.disclosed_at),
                    "title":          r.title,
                    "category":       r.category,
                    "category_label": CATEGORY_LABEL.get(r.category, r.category),
                    "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r.rcept_no}",
                })
            return result
    except Exception as e:
        logger.debug("공시 DB 조회 실패: %s", e)
        return []


def _fetch_disclosures_dart(ticker: str, days: int) -> list[dict]:
    if not Config.DART_API_KEY:
        return []

    corp_map = _get_corp_map()
    corp_code = corp_map.get(ticker)
    if not corp_code:
        return []

    from_date = n_days_ago(days)
    to_date   = today_str()
    # DART API 날짜: YYYYMMDD → 그대로 사용

    result = []
    try:
        resp = requests.get(
            f"{DART_BASE}/list.json",
            params={
                "crtfc_key":  Config.DART_API_KEY,
                "corp_code":  corp_code,
                "bgn_de":     from_date,
                "end_de":     to_date,
                "page_count": 30,
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("status") != "000":
            return []

        for item in data.get("list", []):
            category = item.get("pblntf_ty", "")
            result.append({
                "rcept_no":       item.get("rcept_no", ""),
                "disclosed_at":   _parse_dart_date(item.get("rcept_dt", "")),
                "title":          item.get("report_nm", ""),
                "category":       category,
                "category_label": CATEGORY_LABEL.get(category, category),
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no', '')}",
            })
    except Exception as e:
        logger.error("DART 공시 조회 실패 (%s): %s", ticker, e)

    return result


def _parse_dart_date(date_str: str) -> str:
    """YYYYMMDD → YYYY-MM-DD."""
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str


def save_disclosures_to_db(ticker: str, days: int = 90) -> int:
    """DART 공시를 DB에 저장. 배치용."""
    rows = _fetch_disclosures_dart(ticker, days)
    if not rows:
        return 0

    from db.engine import get_session
    from db.models import DartDisclosure
    from sqlalchemy.dialects.mysql import insert as mysql_insert
    from datetime import datetime

    db_rows = []
    for r in rows:
        try:
            d = datetime.strptime(r["disclosed_at"], "%Y-%m-%d").date()
        except Exception:
            continue
        db_rows.append({
            "rcept_no":     r["rcept_no"],
            "ticker":       ticker,
            "disclosed_at": d,
            "title":        r["title"][:300],
            "category":     r["category"],
        })

    if not db_rows:
        return 0

    with get_session() as s:
        stmt = mysql_insert(DartDisclosure.__table__).values(db_rows)
        stmt = stmt.on_duplicate_key_update(
            title=stmt.inserted.title,
            category=stmt.inserted.category,
        )
        result = s.execute(stmt)
    return result.rowcount
