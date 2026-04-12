"""섹터(업종) 분류 및 적정 배수 서비스.

DART company API의 induty_code(KSIC 기반)를 사용해 종목 섹터를 파악하고
섹터별 적정 PER/PBR 배수를 반환한다.

우선순위:
  KRX 실데이터(pykrx) → 과거 5년 평균 PER/PBR → 섹터 Fallback 테이블
  현재 pykrx 인덱스 API 미동작으로 Fallback 테이블 우선 사용.
"""
import logging
import os
import requests

from cache.ttl_cache import cache

logger = logging.getLogger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"

# ── 섹터 Fallback 배수 테이블 ──────────────────────────────────────────────
# per: 섹터 중간값 사용, pbr: 섹터 중간값 사용

SECTOR_MULTIPLES: dict[str, dict] = {
    "반도체":        {"per": 22.0, "pbr": 2.0},
    "IT·소프트웨어":  {"per": 30.0, "pbr": 4.5},
    "자동차":        {"per": 10.0, "pbr": 1.2},
    "금융·은행":     {"per":  9.0, "pbr": 0.75},
    "유통·소비재":   {"per": 17.5, "pbr": 2.25},
    "에너지·화학":   {"per": 12.5, "pbr": 1.5},
    "바이오·제약":   {"per": 40.0, "pbr": 5.5},
    "통신":          {"per": 11.0, "pbr": 1.25},
    "소재·철강":     {"per": 10.0, "pbr": 0.8},
    "건설·부동산":   {"per": 10.0, "pbr": 0.9},
    "기타":          {"per": 15.0, "pbr": 1.5},
}

# ── KSIC 코드 → 섹터 매핑 ──────────────────────────────────────────────────
# DART induty_code는 KSIC 코드를 따름 (앞 자리 prefix로 섹터 판별)

def _induty_to_sector(code: str | int | None) -> str:
    """DART induty_code(KSIC) → 섹터명 반환."""
    if not code:
        return "기타"
    s = str(code).strip()

    # 길이·접두어 기반 매핑 (KSIC 대·중·소분류 순서로 체크)
    prefixes = [
        # 반도체 / 전자부품 (261, 262, 264, 2612 등)
        ("261",  "반도체"),
        ("262",  "반도체"),
        ("263",  "반도체"),
        ("264",  "반도체"),   # 삼성전자 코드
        ("265",  "반도체"),
        ("2612", "반도체"),
        # IT·소프트웨어 (63=정보서비스, 58=출판/소프트웨어)
        ("631",  "IT·소프트웨어"),
        ("632",  "IT·소프트웨어"),
        ("639",  "IT·소프트웨어"),
        ("58",   "IT·소프트웨어"),
        ("620",  "IT·소프트웨어"),
        ("621",  "IT·소프트웨어"),
        ("622",  "IT·소프트웨어"),
        # 자동차 (301, 302, 303)
        ("301",  "자동차"),
        ("302",  "자동차"),
        ("303",  "자동차"),
        # 바이오·제약 (21=의약품, 86=의료)
        ("211",  "바이오·제약"),
        ("212",  "바이오·제약"),
        ("213",  "바이오·제약"),
        ("21",   "바이오·제약"),
        ("86",   "바이오·제약"),
        # 금융·은행 (64, 65, 66)
        ("641",  "금융·은행"),
        ("642",  "금융·은행"),
        ("649",  "금융·은행"),
        ("651",  "금융·은행"),
        ("652",  "금융·은행"),
        ("659",  "금융·은행"),
        ("661",  "금융·은행"),
        ("64",   "금융·은행"),
        ("65",   "금융·은행"),
        ("66",   "금융·은행"),
        # 통신 (61)
        ("612",  "통신"),
        ("613",  "통신"),
        ("619",  "통신"),
        ("61",   "통신"),
        # 에너지·화학 (20=화학, 19=석유, 35=전기가스)
        ("191",  "에너지·화학"),
        ("192",  "에너지·화학"),
        ("201",  "에너지·화학"),
        ("202",  "에너지·화학"),
        ("203",  "에너지·화학"),
        ("204",  "에너지·화학"),
        ("351",  "에너지·화학"),
        ("352",  "에너지·화학"),
        ("19",   "에너지·화학"),
        ("20",   "에너지·화학"),
        ("35",   "에너지·화학"),
        # 소재·철강 (24=금속, 23=비금속)
        ("241",  "소재·철강"),
        ("242",  "소재·철강"),
        ("243",  "소재·철강"),
        ("231",  "소재·철강"),
        ("24",   "소재·철강"),
        ("23",   "소재·철강"),
        # 유통·소비재 (47=소매, 46=도매, 10=식음료, 13=섬유)
        ("471",  "유통·소비재"),
        ("472",  "유통·소비재"),
        ("479",  "유통·소비재"),
        ("461",  "유통·소비재"),
        ("101",  "유통·소비재"),
        ("102",  "유통·소비재"),
        ("10",   "유통·소비재"),
        ("13",   "유통·소비재"),
        ("47",   "유통·소비재"),
        # 건설·부동산 (41=종합건설, 42=전문건설, 68=부동산)
        ("41",   "건설·부동산"),
        ("42",   "건설·부동산"),
        ("68",   "건설·부동산"),
    ]

    for prefix, sector in prefixes:
        if s.startswith(prefix):
            return sector

    return "기타"


# ── 종목 섹터 조회 ─────────────────────────────────────────────────────────

_SECTOR_CACHE: dict[str, str] = {}   # ticker → sector (메모리 캐시)


def get_ticker_sector(ticker: str) -> str:
    """DART company API로 종목 섹터 반환. 실패 시 '기타'."""
    if ticker in _SECTOR_CACHE:
        return _SECTOR_CACHE[ticker]

    cache_key = f"sector:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        _SECTOR_CACHE[ticker] = cached
        return cached

    sector = "기타"
    try:
        from services.disclosure_service import _get_corp_map
        corp_map  = _get_corp_map()
        corp_code = corp_map.get(ticker)
        if corp_code:
            dart_key = os.environ.get("DART_API_KEY", "")
            r = requests.get(
                f"{DART_BASE}/company.json",
                params={"crtfc_key": dart_key, "corp_code": corp_code},
                timeout=10,
            )
            r.raise_for_status()
            d = r.json()
            if d.get("status") == "000":
                sector = _induty_to_sector(d.get("induty_code"))
    except Exception as e:
        logger.debug("섹터 조회 실패 (%s): %s", ticker, e)

    _SECTOR_CACHE[ticker] = sector
    cache.set(cache_key, sector, ttl=86400 * 30)   # 30일 캐시
    return sector


def get_sector_multiples(ticker: str) -> dict:
    """종목의 섹터별 적정 PER/PBR 반환.

    Returns:
        {"sector": str, "per": float, "pbr": float, "source": str}
    """
    sector = get_ticker_sector(ticker)
    mult   = SECTOR_MULTIPLES.get(sector, SECTOR_MULTIPLES["기타"])
    return {
        "sector": sector,
        "per":    mult["per"],
        "pbr":    mult["pbr"],
        "source": "fallback",   # KRX 실데이터 복구 시 "krx"로 변경
    }
