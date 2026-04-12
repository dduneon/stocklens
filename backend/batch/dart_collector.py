"""
DART 전자공시시스템 재무제표 배치 수집기.
분기 실적 발표 후 1회 실행합니다.

OpenDART API 키 필요: https://opendart.fss.or.kr/

실행:
    python -m batch.dart_collector --year 2024 --quarter 4
    python -m batch.dart_collector --year 2024 --annual
"""
import sys
import os
import logging
import argparse
import time
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import Config
from db.engine import get_session
from db.models import FinancialStatement, BatchLog
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = logging.getLogger("batch.dart")

DART_BASE = "https://opendart.fss.or.kr/api"


class DartClient:
    def __init__(self, api_key: str):
        self._key = api_key
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    def get_corp_codes(self) -> dict[str, str]:
        """종목코드 → DART 고유번호 매핑 반환."""
        import zipfile
        import io
        import xml.etree.ElementTree as ET

        url = f"{DART_BASE}/corpCode.xml"
        resp = self._session.get(url, params={"crtfc_key": self._key}, timeout=30)
        resp.raise_for_status()

        mapping = {}
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            with zf.open(zf.namelist()[0]) as f:
                tree = ET.parse(f)
                for corp in tree.getroot().findall("list"):
                    stock_code = corp.findtext("stock_code", "").strip()
                    corp_code = corp.findtext("corp_code", "").strip()
                    if stock_code:
                        mapping[stock_code] = corp_code
        logger.info("DART 종목코드 매핑 로드: %d건", len(mapping))
        return mapping

    def get_financial_statements(
        self, corp_code: str, year: str, report_code: str
    ) -> list[dict]:
        """단일회사 재무제표 조회 (연결 우선, 없으면 개별).

        report_code:
          11011 - 사업보고서 (연간)
          11012 - 반기보고서
          11013 - 1분기보고서
          11014 - 3분기보고서
        """
        for fs_div in ("CFS", "OFS"):  # 연결 → 개별 순
            params = {
                "crtfc_key": self._key,
                "corp_code": corp_code,
                "bsns_year": year,
                "reprt_code": report_code,
                "fs_div": fs_div,
            }
            try:
                resp = self._session.get(
                    f"{DART_BASE}/fnlttSinglAcntAll.json",
                    params=params,
                    timeout=30,
                )
                data = resp.json()
                if data.get("status") == "000" and data.get("list"):
                    return data["list"]
            except Exception as e:
                logger.debug("DART 조회 실패 (%s %s): %s", corp_code, fs_div, e)
        return []

    def parse_financials(self, items: list[dict]) -> dict:
        """DART 응답에서 주요 계정과목을 추출."""
        result = {
            "revenue": None,
            "operating_income": None,
            "net_income": None,
            "total_assets": None,
            "total_equity": None,
            "total_debt": None,
            "cash": None,
        }

        # XBRL ID 기반 매핑 (우선순위 높음)
        ID_MAP = {
            "ifrs-full_Revenue": "revenue",
            "ifrs-full_ProfitLossFromOperatingActivities": "operating_income",
            "ifrs-full_ProfitLoss": "net_income",
            "ifrs-full_Assets": "total_assets",
            "ifrs-full_Equity": "total_equity",
            "ifrs-full_Liabilities": "total_debt",
            "ifrs-full_CashAndCashEquivalents": "cash",
        }
        # 계정과목명 기반 매핑 — 접두·접미어(손실/비용 등) 무시하고 핵심어로 매핑
        # (keyword, field, must_start_with) — must_start_with=True면 nm이 keyword로 시작해야 함
        NM_KEYWORDS = [
            ("매출액",       "revenue",          True),
            ("영업이익",      "operating_income", True),
            ("당기순이익",    "net_income",       True),   # "당기순이익(손실)" 포함
            ("자산총계",      "total_assets",     True),
            ("자본총계",      "total_equity",     True),   # "부채와자본총계" 제외
            ("부채총계",      "total_debt",       True),
            ("현금및현금성자산", "cash",            True),
        ]

        for item in items:
            account_id = item.get("account_id", "")
            account_nm = item.get("account_nm", "").strip()

            # XBRL ID 우선 매핑
            key = ID_MAP.get(account_id)

            # XBRL ID 없으면 계정과목명 키워드 매핑
            if not key:
                for keyword, field, must_start in NM_KEYWORDS:
                    if must_start:
                        if account_nm.startswith(keyword):
                            key = field
                            break
                    else:
                        if keyword in account_nm:
                            key = field
                            break

            if not key:
                continue

            raw = item.get("thstrm_amount") or item.get("thstrm_add_amount") or ""
            val = _parse_amount(raw)

            # 값이 없거나 0이면 스킵
            if not val:
                continue

            existing = result.get(key)

            # 이미 값이 있으면: 더 큰 절댓값을 선택 (연결 전체 > 지배주주 지분 > 비지배)
            if existing is not None:
                if abs(val) > abs(existing):
                    result[key] = val
            else:
                result[key] = val

        return result


def _parse_amount(s: str) -> int | None:
    if not s:
        return None
    try:
        return int(str(s).replace(",", "").replace(" ", ""))
    except ValueError:
        return None


QUARTER_TO_REPORT = {
    1: "11013",
    2: "11012",
    3: "11014",
    4: "11011",  # 4분기는 사업보고서(연간)
}


def run_dart_batch(year: int, quarter: int | None = None, annual: bool = False) -> None:
    """DART 재무제표 배치 수집.

    Args:
        year: 사업연도
        quarter: 분기 (1~4), None이면 annual 필요
        annual: True면 연간 사업보고서
    """
    api_key = Config.DART_API_KEY
    if not api_key:
        logger.error(".env에 DART_API_KEY를 설정하세요.")
        return

    client = DartClient(api_key)

    # 종목코드 → DART 고유번호 매핑
    try:
        corp_map = client.get_corp_codes()
    except Exception as e:
        logger.error("DART 기업코드 로드 실패: %s", e)
        return

    # 보고서 코드 결정
    if annual or quarter == 4:
        report_code = "11011"
        period_suffix = "A"
        period_label = f"{year}A"
    else:
        report_code = QUARTER_TO_REPORT.get(quarter or 1, "11013")
        period_suffix = f"Q{quarter}"
        period_label = f"{year}Q{quarter}"

    # DB에서 종목 목록 가져오기
    from db.repository import get_ticker_list
    tickers = get_ticker_list()
    logger.info("DART 재무제표 수집 시작: %d 종목, 기간: %s", len(tickers), period_label)

    rows = []
    failed = 0
    for i, t in enumerate(tickers):
        ticker = t["ticker"]
        corp_code = corp_map.get(ticker)
        if not corp_code:
            continue

        try:
            items = client.get_financial_statements(corp_code, str(year), report_code)
            if not items:
                continue
            financials = client.parse_financials(items)
            rows.append({
                "ticker": ticker,
                "period": period_label,
                "period_type": "A" if annual or quarter == 4 else "Q",
                **financials,
            })
        except Exception as e:
            failed += 1
            logger.debug("재무제표 수집 실패 (%s): %s", ticker, e)

        # DART API rate limit 방지 (초당 10건 제한)
        if (i + 1) % 10 == 0:
            time.sleep(1)
            logger.info("진행: %d/%d (실패: %d)", i + 1, len(tickers), failed)

    if rows:
        with get_session() as s:
            stmt = pg_insert(FinancialStatement.__table__).values(rows)
            update_cols = {
                c.name: stmt.excluded[c.name]
                for c in FinancialStatement.__table__.columns
                if c.name not in ("ticker", "period")
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker", "period"], set_=update_cols
            )
            result = s.execute(stmt)
            logger.info("재무제표 upserted: %d rows (실패: %d)", result.rowcount, failed)
    else:
        logger.warning("수집된 재무제표 데이터가 없습니다.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="DART 재무제표 수집기")
    parser.add_argument("--year", type=int, required=True, help="사업연도 (예: 2024)")
    parser.add_argument("--quarter", type=int, choices=[1, 2, 3, 4], help="분기")
    parser.add_argument("--annual", action="store_true", help="연간 사업보고서")
    args = parser.parse_args()

    if not args.quarter and not args.annual:
        parser.error("--quarter 또는 --annual 중 하나를 지정하세요.")

    run_dart_batch(args.year, args.quarter, args.annual)
