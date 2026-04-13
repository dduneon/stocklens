"""
일별 시장 데이터 배치 수집기.
매일 장 마감 후(기본 16:30) pykrx에서 전체 데이터를 수집하여 PostgreSQL에 저장합니다.

실행:
    python -m batch.daily_collector           # 즉시 1회 실행
    python -m batch.daily_collector --schedule # 스케줄러 모드 (daemon)
"""
import sys
import os
import logging
import argparse
from datetime import datetime, timezone

# backend/ 경로 주입
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# pykrx 내부 logging 버그 무시
#   - TypeError: not all arguments converted during string formatting
#   - ValueError: Length mismatch (주말/공휴일 빈 응답)
class _PykrxLogFilter(logging.Filter):
    _SUPPRESS = ("Length mismatch",)

    def filter(self, record):
        try:
            msg = record.getMessage()
            return not any(s in msg for s in self._SUPPRESS)
        except (TypeError, ValueError):
            return False

logging.root.addFilter(_PykrxLogFilter())

from pykrx import stock as krx_stock
from sqlalchemy.dialects.mysql import insert as mysql_insert

from config import Config
from krx_session.manager import login_krx, is_logged_in
from db.engine import engine, get_session
from db.models import (
    Ticker, DailyOHLCV, DailyFundamental,
    DailyMarketCap, DailyInvestorTrading, DailyMarketInvestor, BatchLog,
)
from utils.date_utils import today_str, n_days_ago

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("batch.daily")

MARKETS = ["KOSPI", "KOSDAQ"]


# ── 배치 로그 ──────────────────────────────────────────────────────────────

def _log_start(name: str) -> int:
    with get_session() as s:
        log = BatchLog(batch_name=name, started_at=datetime.now(timezone.utc), status="running")
        s.add(log)
        s.flush()
        return log.id


def _log_done(log_id: int, rows: int) -> None:
    with get_session() as s:
        log = s.get(BatchLog, log_id)
        if log:
            log.finished_at = datetime.now(timezone.utc)
            log.status = "success"
            log.rows_upserted = rows


def _log_fail(log_id: int, err: str) -> None:
    with get_session() as s:
        log = s.get(BatchLog, log_id)
        if log:
            log.finished_at = datetime.now(timezone.utc)
            log.status = "failed"
            log.error_msg = err[:2000]


# ── upsert 헬퍼 ────────────────────────────────────────────────────────────

# tickers 테이블에 없는 종목은 FK 위반 → 캐시로 필터링
_known_tickers: set[str] = set()

def _load_known_tickers(session) -> None:
    global _known_tickers
    if not _known_tickers:
        from sqlalchemy import select
        rows = session.execute(select(Ticker.ticker)).scalars().all()
        _known_tickers = set(rows)

def _filter_by_ticker(rows: list[dict]) -> list[dict]:
    """tickers 테이블에 없는 종목 행 제거."""
    if not _known_tickers:
        return rows
    return [r for r in rows if r.get("ticker") in _known_tickers]

def _upsert(session, model, rows: list[dict], conflict_cols: list[str]) -> int:
    if not rows:
        return 0
    # ticker FK가 있는 테이블이면 필터링
    if "ticker" in conflict_cols and model.__tablename__ != "tickers":
        _load_known_tickers(session)
        rows = _filter_by_ticker(rows)
    if not rows:
        return 0
    stmt = mysql_insert(model.__table__).values(rows)
    update_cols = {
        c.name: stmt.inserted[c.name]
        for c in model.__table__.columns
        if c.name not in conflict_cols
    }
    stmt = stmt.on_duplicate_key_update(**update_cols)
    result = session.execute(stmt)
    return result.rowcount


# ── 1. Ticker 동기화 ───────────────────────────────────────────────────────

def sync_tickers(date_str: str) -> int:
    log_id = _log_start("sync_tickers")
    total = 0
    try:
        rows = []
        for market in MARKETS:
            tickers = krx_stock.get_market_ticker_list(market=market)
            # 섹터 정보
            try:
                # 컬럼: 종목명, 업종명, 종가, 대비, 등락률, 시가총액  /  index: 종목코드
                sectors_df = krx_stock.get_market_sector_classifications(date_str, market=market)
                sector_map = {}
                if not sectors_df.empty:
                    for ticker_code, row in sectors_df.iterrows():
                        sector_map[str(ticker_code)] = {
                            "sector": str(row.get("업종명", "")) or None,
                            "industry": None,
                        }
            except Exception:
                sector_map = {}

            for t in tickers:
                try:
                    name = krx_stock.get_market_ticker_name(t)
                except Exception:
                    name = t
                sec = sector_map.get(t, {})
                rows.append({
                    "ticker": t,
                    "name": name,
                    "market": market,
                    "sector": sec.get("sector"),
                    "industry": sec.get("industry"),
                })

        with get_session() as s:
            total = _upsert(s, Ticker, rows, ["ticker"])
        # 캐시 갱신
        _known_tickers.update(r["ticker"] for r in rows)
        _log_done(log_id, total)
        logger.info("tickers upserted: %d", total)
    except Exception as e:
        _log_fail(log_id, str(e))
        logger.error("sync_tickers 실패: %s", e)
    return total


# ── 2. OHLCV 수집 ──────────────────────────────────────────────────────────
# pykrx get_market_ohlcv 컬럼: 시가, 고가, 저가, 종가, 거래량, 거래대금, 등락률, 시가총액
# index: 티커

def collect_ohlcv(date_str: str) -> int:
    log_id = _log_start("collect_ohlcv")
    total = 0
    try:
        rows = []
        for market in MARKETS:
            try:
                df = krx_stock.get_market_ohlcv(date_str, market=market)
                if df.empty:
                    continue
                df.index.name = "ticker"
                df.reset_index(inplace=True)
                for _, row in df.iterrows():
                    rows.append({
                        "ticker": str(row["ticker"]),
                        "date": date_str,
                        "open": _safe_int(row.get("시가")),
                        "high": _safe_int(row.get("고가")),
                        "low": _safe_int(row.get("저가")),
                        "close": _safe_int(row.get("종가")),
                        "volume": _safe_int(row.get("거래량")),
                        "trading_value": _safe_int(row.get("거래대금")),
                        "change_pct": _safe_float(row.get("등락률")),
                    })
            except Exception as e:
                logger.warning("OHLCV 수집 실패 (%s): %s", market, e)

        # 비거래일(주말/공휴일)이면 close가 모두 0 → 저장 건너뜀
        rows = [r for r in rows if r.get("close")]
        if not rows:
            logger.info("ohlcv: 비거래일(%s), 저장 건너뜀", date_str)
            _log_done(log_id, 0)
            return 0
        with get_session() as s:
            total = _upsert(s, DailyOHLCV, rows, ["ticker", "date"])
        _log_done(log_id, total)
        logger.info("ohlcv upserted: %d rows", total)
    except Exception as e:
        _log_fail(log_id, str(e))
        logger.error("collect_ohlcv 실패: %s", e)
    return total


# ── 3. 펀더멘털 수집 ────────────────────────────────────────────────────────
# pykrx get_market_fundamental 컬럼: BPS, PER, PBR, EPS, DIV, DPS
# index: 티커

def collect_fundamentals(date_str: str) -> int:
    log_id = _log_start("collect_fundamentals")
    total = 0
    try:
        df = krx_stock.get_market_fundamental(date_str, market="ALL")
        if df.empty:
            _log_done(log_id, 0)
            return 0
        df.index.name = "ticker"
        df.reset_index(inplace=True)
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "ticker": str(row["ticker"]),
                "date": date_str,
                "bps": _safe_int(row.get("BPS")),
                "per": _safe_float(row.get("PER")),
                "pbr": _safe_float(row.get("PBR")),
                "eps": _safe_int(row.get("EPS")),
                "div": _safe_float(row.get("DIV")),
                "dps": _safe_int(row.get("DPS")),
            })

        with get_session() as s:
            total = _upsert(s, DailyFundamental, rows, ["ticker", "date"])
        _log_done(log_id, total)
        logger.info("fundamentals upserted: %d rows", total)
    except Exception as e:
        _log_fail(log_id, str(e))
        logger.error("collect_fundamentals 실패: %s", e)
    return total


# ── 4. 시가총액 수집 ────────────────────────────────────────────────────────
# pykrx get_market_cap 컬럼: 종가, 시가총액, 거래량, 거래대금, 상장주식수
# index: 티커

def collect_market_cap(date_str: str) -> int:
    log_id = _log_start("collect_market_cap")
    total = 0
    try:
        rows = []
        for market in MARKETS:
            try:
                df = krx_stock.get_market_cap(date_str, market=market)
                if df.empty:
                    continue
                df.index.name = "ticker"
                df.reset_index(inplace=True)
                for _, row in df.iterrows():
                    rows.append({
                        "ticker": str(row["ticker"]),
                        "date": date_str,
                        "market_cap": _safe_int(row.get("시가총액")),
                        "trading_value": _safe_int(row.get("거래대금")),
                        "listed_shares": _safe_int(row.get("상장주식수")),
                    })
            except Exception as e:
                logger.warning("시가총액 수집 실패 (%s): %s", market, e)

        if rows:
            with get_session() as s:
                total = _upsert(s, DailyMarketCap, rows, ["ticker", "date"])
        _log_done(log_id, total)
        logger.info("market_cap upserted: %d rows", total)
    except Exception as e:
        _log_fail(log_id, str(e))
        logger.error("collect_market_cap 실패: %s", e)
    return total


# ── 5. 투자자별 수급 수집 ──────────────────────────────────────────────────
# pykrx get_market_net_purchases_of_equities_by_ticker(fromdate, todate, market, investor)
# 컬럼: 종목명, 매도거래량, 매수거래량, 순매수거래량, 매도거래대금, 매수거래대금, 순매수거래대금
# index: 티커
# investor: '개인' | '기관합계' | '외국인'  (외국인합계 → 외국인)

_INVESTOR_MAP = [
    ("개인",    "individual"),
    ("기관합계", "institutional"),
    ("외국인",  "foreign"),       # '외국인합계'는 빈 DF 반환 → '외국인' 사용
]

def _fetch_investor(date_str: str, market: str, inv_label: str, inv_key: str) -> dict[str, dict]:
    """단일 (마켓 × 투자자) 조합 API 호출. {ticker: {buy, sell}} 반환."""
    result = {}
    try:
        df = krx_stock.get_market_net_purchases_of_equities_by_ticker(
            date_str, date_str, market, inv_label
        )
        if df.empty:
            return result
        df.index.name = "ticker"
        df.reset_index(inplace=True)
        for _, row in df.iterrows():
            ticker = str(row["ticker"])
            result[ticker] = {
                f"{inv_key}_buy":  _safe_int(row.get("매수거래대금")),
                f"{inv_key}_sell": _safe_int(row.get("매도거래대금")),
            }
    except Exception as e:
        logger.debug("투자자 수급 수집 실패 (%s %s): %s", market, inv_label, e)
    return result


def collect_investor_trading(date_str: str) -> int:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    log_id = _log_start("collect_investor_trading")
    total = 0
    try:
        # 6개 (마켓 × 투자자) 조합을 동시에 호출
        tasks = [
            (market, inv_label, inv_key)
            for market in MARKETS
            for inv_label, inv_key in _INVESTOR_MAP
        ]

        merged: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = {
                executor.submit(_fetch_investor, date_str, market, inv_label, inv_key): inv_key
                for market, inv_label, inv_key in tasks
            }
            for future in as_completed(futures):
                for ticker, cols in future.result().items():
                    if ticker not in merged:
                        merged[ticker] = {"ticker": ticker, "date": date_str}
                    merged[ticker].update(cols)

        # 모든 컬럼이 반드시 존재하도록 기본값 채우기
        _inv_cols = [
            "individual_buy", "individual_sell",
            "institutional_buy", "institutional_sell",
            "foreign_buy", "foreign_sell",
        ]
        merged_rows = [
            {**{c: None for c in _inv_cols}, **row}
            for row in merged.values()
        ]
        if merged_rows:
            with get_session() as s:
                total = _upsert(s, DailyInvestorTrading, merged_rows, ["ticker", "date"])
        _log_done(log_id, total)
        logger.info("investor_trading upserted: %d rows", total)
    except Exception as e:
        _log_fail(log_id, str(e))
        logger.error("collect_investor_trading 실패: %s", e)
    return total


# ── 6. 시장 전체 투자자별 수급 수집 (세부 분류 포함) ──────────────────────
# pykrx get_market_trading_value_by_investor(fromdate, todate, market)
# 반환: index=투자자, columns=매도/매수/순매수

_INVESTOR_DETAIL = [
    "기관합계", "외국인합계", "개인",
    "금융투자", "보험", "투신", "사모", "연기금 등",
]

def collect_market_investor_trading(date_str: str) -> int:
    """시장 단위 투자자별 매매 집계 수집.

    종목별 수급(daily_investor_trading)과 별개로 시장 전체 합산 데이터를
    daily_market_investor 테이블에 저장한다.
    세부 투자자(금융투자/보험/투신/사모/연기금 등) 포함.
    """
    log_id = _log_start("collect_market_investor")
    total = 0
    try:
        rows = []
        for market in MARKETS:
            try:
                df = krx_stock.get_market_trading_value_by_investor(
                    date_str, date_str, market
                )
                if df.empty:
                    continue
                for investor in _INVESTOR_DETAIL:
                    if investor not in df.index:
                        continue
                    r = df.loc[investor]
                    rows.append({
                        "market":   market,
                        "date":     date_str,
                        "investor": investor,
                        "buy":      _safe_int(r.get("매수")),
                        "sell":     _safe_int(r.get("매도")),
                        "net":      _safe_int(r.get("순매수")),
                    })
            except Exception as e:
                logger.warning("시장 투자자 수급 수집 실패 (%s): %s", market, e)

        if rows:
            with get_session() as s:
                total = _upsert(s, DailyMarketInvestor, rows, ["market", "date", "investor"])
        _log_done(log_id, total)
        logger.info("market_investor upserted: %d rows", total)
    except Exception as e:
        _log_fail(log_id, str(e))
        logger.error("collect_market_investor_trading 실패: %s", e)
    return total


# ── 전체 배치 실행 ──────────────────────────────────────────────────────────

def run_daily_batch(date_str: str | None = None) -> None:
    date_str = date_str or today_str()
    logger.info("===== 일별 배치 시작: %s =====", date_str)
    t0 = datetime.now()

    sync_tickers(date_str)
    collect_ohlcv(date_str)
    collect_fundamentals(date_str)
    collect_market_cap(date_str)
    collect_investor_trading(date_str)
    collect_market_investor_trading(date_str)

    elapsed = (datetime.now() - t0).total_seconds()
    logger.info("===== 일별 배치 완료: %.1f초 =====", elapsed)


# ── 과거 데이터 초기 적재 (최초 1회) ──────────────────────────────────────

def run_historical_load(days: int = 365) -> None:
    """최초 실행 시 과거 N일치 OHLCV 및 펀더멘털 적재."""
    logger.info("===== 과거 데이터 적재 시작 (%d일) =====", days)

    # 종목 목록 먼저 동기화
    sync_tickers(today_str())

    from utils.date_utils import n_days_ago
    for market in MARKETS:
        from_date = n_days_ago(days)
        to_date = today_str()
        try:
            logger.info("OHLCV 과거 데이터 로드: %s %s~%s", market, from_date, to_date)
            df = krx_stock.get_market_ohlcv(from_date, to_date, market=market)
            # pykrx 기간조회 반환 형식: 날짜 인덱스
            if not df.empty:
                df.index.name = "date"
                df.reset_index(inplace=True)
                # 이 방식은 단일 날짜 반복이 더 안정적
        except Exception as e:
            logger.warning("과거 OHLCV 로드 실패 (%s): %s", market, e)

    logger.info("과거 데이터 적재는 날짜별 반복 방식을 권장합니다.")
    logger.info("run_backfill(days=%d) 를 대신 사용하세요.", days)


def _get_trading_dates(from_date: str, to_date: str) -> list[str]:
    """실제 거래일 목록만 반환 (삼성전자 기준으로 비거래일 사전 제거)."""
    try:
        df = krx_stock.get_market_ohlcv(from_date, to_date, "005930")
        if not df.empty:
            return [d.strftime("%Y%m%d") for d in df.index]
    except Exception as e:
        logger.warning("거래일 캘린더 조회 실패, 전체 날짜 순회로 fallback: %s", e)

    # fallback: 전체 날짜 반환 (비거래일은 collect_ohlcv에서 걸러짐)
    from datetime import timedelta
    start = datetime.strptime(from_date, "%Y%m%d").date()
    end   = datetime.strptime(to_date,   "%Y%m%d").date()
    result, cur = [], start
    while cur <= end:
        result.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)
    return result


def _backfill_one_date(date_str: str) -> bool:
    """단일 날짜 backfill. 성공 여부 반환."""
    try:
        ohlcv_cnt = collect_ohlcv(date_str)
        if ohlcv_cnt == 0:
            return False  # 비거래일
        collect_fundamentals(date_str)
        collect_market_cap(date_str)
        collect_investor_trading(date_str)
        collect_market_investor_trading(date_str)
        return True
    except Exception as e:
        logger.warning("backfill 실패 (%s): %s", date_str, e)
        return False


def run_backfill(days: int = 30, workers: int = 4) -> None:
    """과거 N일치 데이터를 병렬로 빠르게 적재.

    Args:
        days:    소급 수집할 일수
        workers: 병렬 스레드 수 (KRX 부하 고려, 기본 4)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    logger.info("종목 목록 동기화 중...")
    sync_tickers(today_str())

    from_date = n_days_ago(days)
    to_date   = today_str()

    logger.info("거래일 캘린더 조회 중 (%s ~ %s)...", from_date, to_date)
    trading_dates = _get_trading_dates(from_date, to_date)
    logger.info("실제 거래일 %d일 확인 → %d workers로 병렬 수집 시작",
                len(trading_dates), workers)

    done, failed = 0, 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_backfill_one_date, d): d for d in trading_dates}
        for future in as_completed(futures):
            date_str = futures[future]
            success = future.result()
            if success:
                done += 1
                logger.info("✓ %s (%d/%d)", date_str, done + failed, len(trading_dates))
            else:
                failed += 1

    logger.info("backfill 완료 — 성공: %d일, 건너뜀/실패: %d일", done, failed)


# ── 스케줄러 ────────────────────────────────────────────────────────────────

def run_scheduler() -> None:
    import schedule
    import time

    logger.info("스케줄러 시작 (매일 16:30 배치 실행)")
    schedule.every().day.at("16:30").do(run_daily_batch)

    while True:
        schedule.run_pending()
        time.sleep(30)


# ── 유틸 ───────────────────────────────────────────────────────────────────

def _safe_int(v) -> int | None:
    try:
        if v is None:
            return None
        import math
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else int(f)
    except (TypeError, ValueError):
        return None


def _safe_float(v) -> float | None:
    try:
        if v is None:
            return None
        import math
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


# ── 엔트리포인트 ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StockLens 일별 배치 수집기")
    parser.add_argument("--schedule", action="store_true", help="스케줄러 모드 (daemon)")
    parser.add_argument("--backfill", type=int, metavar="DAYS", help="과거 N일 데이터 적재")
    parser.add_argument("--workers", type=int, default=4, metavar="N", help="backfill 병렬 스레드 수 (기본 4)")
    parser.add_argument("--date", type=str, help="특정 날짜 수집 (YYYYMMDD)")
    args = parser.parse_args()

    # KRX 로그인
    if not Config.KRX_LOGIN_ID or not Config.KRX_LOGIN_PW:
        logger.error(".env에 KRX_LOGIN_ID, KRX_LOGIN_PW를 설정하세요.")
        sys.exit(1)

    logger.info("KRX 로그인 시도...")
    if not login_krx(Config.KRX_LOGIN_ID, Config.KRX_LOGIN_PW):
        logger.error("KRX 로그인 실패")
        sys.exit(1)

    if args.backfill:
        run_backfill(args.backfill, workers=args.workers)
    elif args.schedule:
        run_scheduler()
    else:
        run_daily_batch(args.date)
