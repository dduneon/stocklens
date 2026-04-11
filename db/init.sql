-- StockLens PostgreSQL 초기 스키마

-- ── 종목 기본 정보 ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tickers (
    ticker      VARCHAR(10)  PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    market      VARCHAR(10)  NOT NULL,   -- KOSPI / KOSDAQ
    sector      VARCHAR(100),
    industry    VARCHAR(100),
    updated_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- ── 일별 OHLCV ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_ohlcv (
    ticker          VARCHAR(10)  NOT NULL REFERENCES tickers(ticker) ON DELETE CASCADE,
    date            DATE         NOT NULL,
    open            BIGINT,
    high            BIGINT,
    low             BIGINT,
    close           BIGINT,
    volume          BIGINT,
    trading_value   BIGINT,
    change_pct      NUMERIC(8,4),
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_ohlcv_date ON daily_ohlcv(date);

-- ── 일별 펀더멘털 ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_fundamental (
    ticker      VARCHAR(10)  NOT NULL REFERENCES tickers(ticker) ON DELETE CASCADE,
    date        DATE         NOT NULL,
    bps         BIGINT,
    per         NUMERIC(10,4),
    pbr         NUMERIC(10,4),
    eps         BIGINT,
    div         NUMERIC(8,4),   -- 배당수익률 (%)
    dps         BIGINT,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_fundamental_date ON daily_fundamental(date);

-- ── 일별 시가총액 ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_market_cap (
    ticker          VARCHAR(10)  NOT NULL REFERENCES tickers(ticker) ON DELETE CASCADE,
    date            DATE         NOT NULL,
    market_cap      BIGINT,
    listed_shares   BIGINT,
    trading_value   BIGINT,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_cap_date ON daily_market_cap(date);

-- ── 일별 투자자별 수급 ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_investor_trading (
    ticker              VARCHAR(10)  NOT NULL REFERENCES tickers(ticker) ON DELETE CASCADE,
    date                DATE         NOT NULL,
    individual_buy      BIGINT,
    individual_sell     BIGINT,
    institutional_buy   BIGINT,
    institutional_sell  BIGINT,
    foreign_buy         BIGINT,
    foreign_sell        BIGINT,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_investor_date ON daily_investor_trading(date);

-- ── 재무제표 (DART, 분기별) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS financial_statement (
    ticker          VARCHAR(10)  NOT NULL REFERENCES tickers(ticker) ON DELETE CASCADE,
    period          VARCHAR(10)  NOT NULL,  -- 예: 2024Q1, 2024A (연간)
    period_type     VARCHAR(5)   NOT NULL,  -- Q (분기) / A (연간)
    revenue         BIGINT,
    operating_income BIGINT,
    net_income      BIGINT,
    total_assets    BIGINT,
    total_equity    BIGINT,
    total_debt      BIGINT,
    cash            BIGINT,
    updated_at      TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (ticker, period)
);

-- ── 배치 실행 로그 ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS batch_log (
    id          SERIAL       PRIMARY KEY,
    batch_name  VARCHAR(50)  NOT NULL,
    started_at  TIMESTAMPTZ  NOT NULL,
    finished_at TIMESTAMPTZ,
    status      VARCHAR(20)  NOT NULL DEFAULT 'running',  -- running / success / failed
    rows_upserted INT        DEFAULT 0,
    error_msg   TEXT
);
