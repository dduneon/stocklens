"""SQLAlchemy ORM 모델."""
from datetime import date, datetime
from sqlalchemy import (
    BigInteger, Column, Date, Integer, Numeric,
    String, Text, DateTime, ForeignKey, func,
)
from db.engine import Base


class Ticker(Base):
    __tablename__ = "tickers"

    ticker     = Column(String(10), primary_key=True)
    name       = Column(String(100), nullable=False)
    market     = Column(String(10), nullable=False)
    sector     = Column(String(100))
    industry   = Column(String(100))
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())


class DailyOHLCV(Base):
    __tablename__ = "daily_ohlcv"

    ticker        = Column(String(10), ForeignKey("tickers.ticker", ondelete="CASCADE"), primary_key=True)
    date          = Column(Date, primary_key=True)
    open          = Column(BigInteger)
    high          = Column(BigInteger)
    low           = Column(BigInteger)
    close         = Column(BigInteger)
    volume        = Column(BigInteger)
    trading_value = Column(BigInteger)
    change_pct    = Column(Numeric(8, 4))


class DailyFundamental(Base):
    __tablename__ = "daily_fundamental"

    ticker = Column(String(10), ForeignKey("tickers.ticker", ondelete="CASCADE"), primary_key=True)
    date   = Column(Date, primary_key=True)
    bps    = Column(BigInteger)
    per    = Column(Numeric(10, 4))
    pbr    = Column(Numeric(10, 4))
    eps    = Column(BigInteger)
    div    = Column(Numeric(8, 4))
    dps    = Column(BigInteger)


class DailyMarketCap(Base):
    __tablename__ = "daily_market_cap"

    ticker          = Column(String(10), ForeignKey("tickers.ticker", ondelete="CASCADE"), primary_key=True)
    date            = Column(Date, primary_key=True)
    market_cap      = Column(BigInteger)
    listed_shares   = Column(BigInteger)
    trading_value   = Column(BigInteger)


class DailyInvestorTrading(Base):
    __tablename__ = "daily_investor_trading"

    ticker             = Column(String(10), ForeignKey("tickers.ticker", ondelete="CASCADE"), primary_key=True)
    date               = Column(Date, primary_key=True)
    individual_buy     = Column(BigInteger)
    individual_sell    = Column(BigInteger)
    institutional_buy  = Column(BigInteger)
    institutional_sell = Column(BigInteger)
    foreign_buy        = Column(BigInteger)
    foreign_sell       = Column(BigInteger)


class FinancialStatement(Base):
    __tablename__ = "financial_statement"

    ticker           = Column(String(10), ForeignKey("tickers.ticker", ondelete="CASCADE"), primary_key=True)
    period           = Column(String(10), primary_key=True)
    period_type      = Column(String(5), nullable=False)
    revenue          = Column(BigInteger)
    operating_income = Column(BigInteger)
    net_income       = Column(BigInteger)
    total_assets     = Column(BigInteger)
    total_equity     = Column(BigInteger)
    total_debt       = Column(BigInteger)
    cash             = Column(BigInteger)
    updated_at       = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())


class DailyShorting(Base):
    """일별 공매도 데이터 (pykrx)."""
    __tablename__ = "daily_shorting"

    ticker          = Column(String(10), ForeignKey("tickers.ticker", ondelete="CASCADE"), primary_key=True)
    date            = Column(Date, primary_key=True)
    shorting_volume = Column(BigInteger)   # 공매도 거래량
    total_volume    = Column(BigInteger)   # 전체 거래량
    shorting_ratio  = Column(Numeric(8, 4))  # 공매도 비율 (%)
    balance         = Column(BigInteger)   # 공매도 잔고 수량
    balance_value   = Column(BigInteger)   # 잔고 금액


class DartDisclosure(Base):
    """DART 주요 공시 목록."""
    __tablename__ = "dart_disclosure"

    rcept_no     = Column(String(20), primary_key=True)   # 접수번호
    ticker       = Column(String(10), ForeignKey("tickers.ticker", ondelete="CASCADE"), index=True)
    disclosed_at = Column(Date, index=True)
    title        = Column(String(300))
    category     = Column(String(50))    # 공시 유형 코드


class MacroIndicator(Base):
    """ECOS 거시경제 지표."""
    __tablename__ = "macro_indicator"

    indicator = Column(String(50), primary_key=True)  # 'base_rate' | 'usd_krw' | 'cpi'
    date      = Column(Date, primary_key=True)
    value     = Column(Numeric(14, 4))


class BatchLog(Base):
    __tablename__ = "batch_log"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    batch_name    = Column(String(50), nullable=False)
    started_at    = Column(DateTime(timezone=True), nullable=False)
    finished_at   = Column(DateTime(timezone=True))
    status        = Column(String(20), nullable=False, default="running")
    rows_upserted = Column(Integer, default=0)
    error_msg     = Column(Text)
