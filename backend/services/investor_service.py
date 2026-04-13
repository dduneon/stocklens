"""투자자별 매매 동향 서비스.

DB 우선 → pykrx fallback 원칙.
- daily_investor_trading 테이블에 64만건 수집 완료 (배치)
- 종목별 flow/summary: DB
- 시장 전체 요약: DB 집계
- 섹터 핫: DB 집계 + KRX sector_classifications (등락률)
"""
import logging
from datetime import datetime, timedelta

from pykrx import stock as krx_stock

from cache.ttl_cache import cache
from config import Config
from utils.date_utils import n_days_ago, latest_trading_date, fmt_datetime
import db.repository as repo

logger = logging.getLogger(__name__)


def _yyyymmdd(date_str: str) -> str:
    """'2026-04-10' → '20260410'"""
    return date_str.replace("-", "")


# ── 종목별 투자자 일별 순매수 ──────────────────────────────────────────────

def get_stock_investor_flow(
    ticker: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """종목별 기관/외국인/개인 일별 순매수 (거래대금).

    DB 우선, 없으면 pykrx fallback.
    """
    from_date = from_date or n_days_ago(60)
    to_date   = to_date   or latest_trading_date()
    cache_key = f"investor_flow:{ticker}:{from_date}:{to_date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # DB 우선
    rows = repo.get_investor_trading(ticker, from_date, to_date)
    if rows:
        result = [
            {
                "date":        r["date"][:10],
                "institution": (r.get("institutional_buy") or 0) - (r.get("institutional_sell") or 0),
                "foreign":     (r.get("foreign_buy") or 0)       - (r.get("foreign_sell") or 0),
                "individual":  (r.get("individual_buy") or 0)    - (r.get("individual_sell") or 0),
            }
            for r in rows
        ]
        cache.set(cache_key, result, ttl=Config.CACHE_TTL_MARKET)
        return result

    # fallback: pykrx
    try:
        df = krx_stock.get_market_trading_value_by_date(
            _yyyymmdd(from_date), _yyyymmdd(to_date), ticker
        )
        if df.empty:
            return []
        df.index.name = "date"
        df.reset_index(inplace=True)
        df["date"] = df["date"].apply(fmt_datetime)
        result = [
            {
                "date":        row["date"],
                "institution": int(row.get("기관합계", 0) or 0),
                "foreign":     int(row.get("외국인합계", 0) or 0),
                "individual":  int(row.get("개인", 0) or 0),
            }
            for _, row in df.iterrows()
        ]
        cache.set(cache_key, result, ttl=Config.CACHE_TTL_MARKET)
        return result
    except Exception as e:
        logger.error("종목 투자자 수급 조회 실패 (%s): %s", ticker, e)
        return []


def get_stock_investor_summary(
    ticker: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """종목별 기간 합산 투자자 현황.

    DB에서 집계. 없으면 pykrx fallback.
    """
    from_date = from_date or n_days_ago(20)
    to_date   = to_date   or latest_trading_date()
    cache_key = f"investor_summary:{ticker}:{from_date}:{to_date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    rows = repo.get_investor_trading(ticker, from_date, to_date)
    if rows:
        totals = {"institutional_buy": 0, "institutional_sell": 0,
                  "foreign_buy": 0, "foreign_sell": 0,
                  "individual_buy": 0, "individual_sell": 0}
        for r in rows:
            for k in totals:
                totals[k] += r.get(k) or 0

        summary_rows = [
            {
                "investor": "기관합계",
                "buy":  totals["institutional_buy"],
                "sell": totals["institutional_sell"],
                "net":  totals["institutional_buy"] - totals["institutional_sell"],
            },
            {
                "investor": "외국인합계",
                "buy":  totals["foreign_buy"],
                "sell": totals["foreign_sell"],
                "net":  totals["foreign_buy"] - totals["foreign_sell"],
            },
            {
                "investor": "개인",
                "buy":  totals["individual_buy"],
                "sell": totals["individual_sell"],
                "net":  totals["individual_buy"] - totals["individual_sell"],
            },
        ]
        result = {"rows": summary_rows, "from_date": from_date, "to_date": to_date}
        cache.set(cache_key, result, ttl=Config.CACHE_TTL_MARKET)
        return result

    # fallback: pykrx (세부 분류는 pykrx만 가능)
    try:
        df = krx_stock.get_market_trading_value_by_investor(
            _yyyymmdd(from_date), _yyyymmdd(to_date), ticker
        )
        if df.empty:
            return {"rows": []}

        SHOW = ["기관합계", "외국인합계", "개인", "금융투자", "보험", "투신", "연기금 등"]
        summary_rows = []
        for investor in SHOW:
            if investor in df.index:
                r = df.loc[investor]
                summary_rows.append({
                    "investor": investor,
                    "sell": int(r.get("매도", 0) or 0),
                    "buy":  int(r.get("매수", 0) or 0),
                    "net":  int(r.get("순매수", 0) or 0),
                })
        result = {"rows": summary_rows, "from_date": from_date, "to_date": to_date}
        cache.set(cache_key, result, ttl=Config.CACHE_TTL_MARKET)
        return result
    except Exception as e:
        logger.error("종목 투자자 합산 조회 실패 (%s): %s", ticker, e)
        return {"rows": []}


# ── 시장 전체 투자자 현황 ──────────────────────────────────────────────────

def get_market_investor_summary(market: str = "KOSPI", days: int = 1) -> dict:
    """시장 전체 투자자별 매도/매수/순매수.

    DB에서 날짜 범위 집계. 없으면 pykrx fallback.
    """
    # daily_market_investor 자체의 최신 날짜 기준으로 조회
    # (daily_ohlcv 기준 latest_trading_date와 다를 수 있음 — 비거래일 수동 수집 포함)
    from db.engine import get_session
    from sqlalchemy import select, and_, func

    try:
        from db.models import DailyMarketInvestor as _DMI
        with get_session() as _s:
            _latest = _s.execute(
                select(func.max(_DMI.date)).where(_DMI.market == market)
            ).scalar()
        to_date = _latest.strftime("%Y%m%d") if _latest else latest_trading_date()
    except Exception:
        to_date = latest_trading_date()

    from_date = n_days_ago(days + 5)  # 주말 여유
    cache_key = f"market_investor:{market}:{to_date}:{days}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    fd = datetime.strptime(from_date, "%Y%m%d").date()
    td = datetime.strptime(to_date, "%Y%m%d").date()

    # pykrx 버전에 따라 "외국인합계" 또는 "외국인" 으로 반환될 수 있으므로 둘 다 허용
    # 표시 우선순위: 기관합계 → 외국인합계(또는 외국인) → 개인 → 세부분류
    SHOW_ORDER = ["기관합계", "외국인합계", "외국인", "개인", "금융투자", "보험", "투신", "사모", "연기금 등"]

    # 1순위: daily_market_investor (세부 분류 포함, 배치 수집 후 사용 가능)
    try:
        from db.models import DailyMarketInvestor
        with get_session() as s:
            q = (
                select(
                    DailyMarketInvestor.investor,
                    func.sum(DailyMarketInvestor.buy).label("buy"),
                    func.sum(DailyMarketInvestor.sell).label("sell"),
                    func.sum(DailyMarketInvestor.net).label("net"),
                )
                .where(
                    and_(
                        DailyMarketInvestor.market == market,
                        DailyMarketInvestor.date >= fd,
                        DailyMarketInvestor.date <= td,
                    )
                )
                .group_by(DailyMarketInvestor.investor)
            )
            db_rows = {r.investor: r for r in s.execute(q).all()}

        # 외국인합계 또는 외국인 둘 중 하나라도 있어야 유효한 데이터로 간주
        has_foreign = "외국인합계" in db_rows or "외국인" in db_rows
        if db_rows and has_foreign:
            rows = [
                {
                    # "외국인" → 프론트에서 "외국인합계" 카드에 표시되도록 레이블 통일
                    "investor": "외국인합계" if inv == "외국인" else inv,
                    "buy":  int(db_rows[inv].buy  or 0),
                    "sell": int(db_rows[inv].sell or 0),
                    "net":  int(db_rows[inv].net  or 0),
                }
                for inv in SHOW_ORDER
                if inv in db_rows
            ]
            if rows:
                result = {"rows": rows, "market": market, "date": to_date}
                cache.set(cache_key, result, ttl=Config.CACHE_TTL_MARKET)
                return result
    except Exception as e:
        logger.warning("시장 투자자 DB 조회 실패 (daily_market_investor): %s", e)

    # 2순위: daily_investor_trading 집계 (기관합계/외국인합계/개인 3종)
    try:
        from db.models import DailyInvestorTrading, Ticker
        with get_session() as s:
            q = (
                select(
                    func.sum(DailyInvestorTrading.institutional_buy).label("inst_buy"),
                    func.sum(DailyInvestorTrading.institutional_sell).label("inst_sell"),
                    func.sum(DailyInvestorTrading.foreign_buy).label("for_buy"),
                    func.sum(DailyInvestorTrading.foreign_sell).label("for_sell"),
                    func.sum(DailyInvestorTrading.individual_buy).label("ind_buy"),
                    func.sum(DailyInvestorTrading.individual_sell).label("ind_sell"),
                )
                .join(Ticker, Ticker.ticker == DailyInvestorTrading.ticker)
                .where(
                    and_(
                        DailyInvestorTrading.date >= fd,
                        DailyInvestorTrading.date <= td,
                        Ticker.market == market,
                    )
                )
            )
            row = s.execute(q).one()

        if row and row.inst_buy:
            rows = [
                {"investor": "기관합계",
                 "buy": int(row.inst_buy or 0), "sell": int(row.inst_sell or 0),
                 "net": int((row.inst_buy or 0) - (row.inst_sell or 0))},
                {"investor": "외국인합계",
                 "buy": int(row.for_buy or 0), "sell": int(row.for_sell or 0),
                 "net": int((row.for_buy or 0) - (row.for_sell or 0))},
                {"investor": "개인",
                 "buy": int(row.ind_buy or 0), "sell": int(row.ind_sell or 0),
                 "net": int((row.ind_buy or 0) - (row.ind_sell or 0))},
            ]
            result = {"rows": rows, "market": market, "date": to_date}
            # 2순위 결과(세부분류 없음)는 짧게 캐시 → 배치 후 빠르게 갱신
            cache.set(cache_key, result, ttl=60)
            return result
    except Exception as e:
        logger.warning("시장 투자자 DB 집계 실패 (daily_investor_trading): %s", e)

    # 3순위: pykrx fallback (금융투자/보험/투신 등 세부 분류)
    try:
        df = krx_stock.get_market_trading_value_by_investor(
            _yyyymmdd(from_date), _yyyymmdd(to_date), market
        )
        if df.empty:
            return {"rows": [], "market": market}

        SHOW = ["기관합계", "외국인합계", "개인", "금융투자", "보험", "투신", "사모", "연기금 등"]
        rows = []
        for investor in SHOW:
            if investor in df.index:
                r = df.loc[investor]
                rows.append({
                    "investor": investor,
                    "sell": int(r.get("매도", 0) or 0),
                    "buy":  int(r.get("매수", 0) or 0),
                    "net":  int(r.get("순매수", 0) or 0),
                })

        result = {"rows": rows, "market": market, "date": to_date}
        cache.set(cache_key, result, ttl=Config.CACHE_TTL_MARKET)
        return result
    except Exception as e:
        logger.error("시장 투자자 현황 조회 실패 (%s): %s", market, e)
        return {"rows": [], "market": market}


# ── 섹터 핫 분석 ──────────────────────────────────────────────────────────

def get_sector_heat(market: str = "KOSPI", days: int = 5) -> dict:
    """어떤 섹터가 핫한가.

    - 섹터별 평균 등락률: KRX sector_classifications (당일 실시간)
    - 섹터별 외국인/기관 순매수: DB에서 날짜 범위 집계
    """
    to_date   = latest_trading_date()
    from_date = n_days_ago(days + 5)
    cache_key = f"sector_heat:{market}:{to_date}:{days}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from services.sector_service import _KRX_업종_TO_SECTOR

        # 1. 당일 섹터별 등락률/시가총액 (KRX)
        df_sec = krx_stock.get_market_sector_classifications(to_date, market=market)
        if df_sec.empty:
            return {"date": to_date, "sectors": []}

        # 2. 업종별 집계 구조 + ticker→업종 역매핑
        sector_stats: dict[str, dict] = {}
        ticker_to_업종: dict[str, str] = {}

        for ticker_code, row in df_sec.iterrows():
            업종명   = str(row.get("업종명", "")).strip()
            등락률   = float(row.get("등락률", 0) or 0)
            시가총액 = float(row.get("시가총액", 0) or 0)
            t = str(ticker_code)
            ticker_to_업종[t] = 업종명

            if 업종명 not in sector_stats:
                sector_stats[업종명] = {
                    "krx_name":        업종명,
                    "sector":          _KRX_업종_TO_SECTOR.get(업종명, "기타"),
                    "change_sum":      0.0,
                    "total_mktcap":    0.0,
                    "stock_count":     0,
                    "foreign_net":     0,
                    "institution_net": 0,
                }
            s = sector_stats[업종명]
            s["change_sum"]   += 등락률
            s["total_mktcap"] += 시가총액
            s["stock_count"]  += 1

        for s in sector_stats.values():
            s["avg_change"] = round(s["change_sum"] / max(s["stock_count"], 1), 2)
            del s["change_sum"]

        # 3. DB에서 날짜 범위 전체 종목 투자자 합산
        try:
            from db.engine import get_session
            from db.models import DailyInvestorTrading, Ticker
            from sqlalchemy import select, and_, func

            fd = datetime.strptime(from_date, "%Y%m%d").date()
            td = datetime.strptime(to_date,   "%Y%m%d").date()

            with get_session() as s_db:
                q = (
                    select(
                        DailyInvestorTrading.ticker,
                        func.sum(DailyInvestorTrading.institutional_buy
                                 - DailyInvestorTrading.institutional_sell).label("inst_net"),
                        func.sum(DailyInvestorTrading.foreign_buy
                                 - DailyInvestorTrading.foreign_sell).label("for_net"),
                    )
                    .join(Ticker, Ticker.ticker == DailyInvestorTrading.ticker)
                    .where(
                        and_(
                            DailyInvestorTrading.date >= fd,
                            DailyInvestorTrading.date <= td,
                            Ticker.market == market,
                        )
                    )
                    .group_by(DailyInvestorTrading.ticker)
                )
                db_rows = s_db.execute(q).all()

            for db_row in db_rows:
                업종명 = ticker_to_업종.get(str(db_row.ticker), "")
                if 업종명 and 업종명 in sector_stats:
                    sector_stats[업종명]["institution_net"] += int(db_row.inst_net or 0)
                    sector_stats[업종명]["foreign_net"]     += int(db_row.for_net or 0)

        except Exception as e:
            logger.warning("섹터 수급 DB 집계 실패, pykrx fallback: %s", e)
            # pykrx fallback
            for investor_key, col in [("외국인", "foreign_net"), ("기관합계", "institution_net")]:
                try:
                    df_inv = krx_stock.get_market_net_purchases_of_equities_by_ticker(
                        _yyyymmdd(from_date), _yyyymmdd(to_date), market, investor_key
                    )
                    for t_code, irow in df_inv.iterrows():
                        업종명 = ticker_to_업종.get(str(t_code), "")
                        if 업종명 and 업종명 in sector_stats:
                            sector_stats[업종명][col] += int(irow.get("순매수거래대금", 0) or 0)
                except Exception as e2:
                    logger.warning("pykrx 투자자 fallback 실패 (%s): %s", investor_key, e2)

        # 4. 결과 정렬 (외국인 순매수 내림차순)
        sectors = sorted(
            [
                {
                    "krx_name":        s["krx_name"],
                    "sector":          s["sector"],
                    "avg_change":      s["avg_change"],
                    "total_mktcap":    int(s["total_mktcap"]),
                    "stock_count":     s["stock_count"],
                    "foreign_net":     s["foreign_net"],
                    "institution_net": s["institution_net"],
                }
                for s in sector_stats.values()
            ],
            key=lambda x: x["foreign_net"],
            reverse=True,
        )

        result = {"date": to_date, "market": market, "days": days, "sectors": sectors}
        cache.set(cache_key, result, ttl=Config.CACHE_TTL_MARKET)
        return result

    except Exception as e:
        logger.error("섹터 핫 분석 실패 (%s): %s", market, e)
        return {"date": to_date, "sectors": []}
