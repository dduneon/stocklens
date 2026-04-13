-- StockLens MariaDB 초기 스키마
-- utf8mb4: 한국어 + 이모지 완전 지원

CREATE DATABASE IF NOT EXISTS stocklens CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE stocklens;

-- ── 종목 기본 정보 ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tickers (
    ticker      VARCHAR(10)  NOT NULL,
    name        VARCHAR(100) NOT NULL,
    market      VARCHAR(10)  NOT NULL,
    sector      VARCHAR(100),
    industry    VARCHAR(100),
    updated_at  DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── 일별 OHLCV ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_ohlcv (
    ticker          VARCHAR(10)  NOT NULL,
    date            DATE         NOT NULL,
    open            BIGINT,
    high            BIGINT,
    low             BIGINT,
    close           BIGINT,
    volume          BIGINT,
    trading_value   BIGINT,
    change_pct      DECIMAL(8,4),
    PRIMARY KEY (ticker, date),
    CONSTRAINT fk_ohlcv_ticker FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE INDEX IF NOT EXISTS idx_ohlcv_date ON daily_ohlcv(date);

-- ── 일별 펀더멘털 ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_fundamental (
    ticker      VARCHAR(10)  NOT NULL,
    date        DATE         NOT NULL,
    bps         BIGINT,
    per         DECIMAL(10,4),
    pbr         DECIMAL(10,4),
    eps         BIGINT,
    `div`       DECIMAL(8,4),
    dps         BIGINT,
    PRIMARY KEY (ticker, date),
    CONSTRAINT fk_fund_ticker FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE INDEX IF NOT EXISTS idx_fundamental_date ON daily_fundamental(date);

-- ── 일별 시가총액 ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_market_cap (
    ticker          VARCHAR(10)  NOT NULL,
    date            DATE         NOT NULL,
    market_cap      BIGINT,
    listed_shares   BIGINT,
    trading_value   BIGINT,
    PRIMARY KEY (ticker, date),
    CONSTRAINT fk_cap_ticker FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE INDEX IF NOT EXISTS idx_cap_date ON daily_market_cap(date);

-- ── 일별 투자자별 수급 ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_investor_trading (
    ticker              VARCHAR(10)  NOT NULL,
    date                DATE         NOT NULL,
    individual_buy      BIGINT,
    individual_sell     BIGINT,
    institutional_buy   BIGINT,
    institutional_sell  BIGINT,
    foreign_buy         BIGINT,
    foreign_sell        BIGINT,
    PRIMARY KEY (ticker, date),
    CONSTRAINT fk_inv_ticker FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE INDEX IF NOT EXISTS idx_investor_date ON daily_investor_trading(date);

-- ── 시장 전체 투자자별 수급 (세부 분류) ───────────────────────────────
CREATE TABLE IF NOT EXISTS daily_market_investor (
    market      VARCHAR(10)  NOT NULL,
    date        DATE         NOT NULL,
    investor    VARCHAR(20)  NOT NULL,
    buy         BIGINT,
    sell        BIGINT,
    net         BIGINT,
    PRIMARY KEY (market, date, investor)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE INDEX IF NOT EXISTS idx_mkt_inv_date ON daily_market_investor(date);

-- ── 일별 공매도 ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_shorting (
    ticker          VARCHAR(10)  NOT NULL,
    date            DATE         NOT NULL,
    shorting_volume BIGINT,
    total_volume    BIGINT,
    shorting_ratio  DECIMAL(8,4),
    balance         BIGINT,
    balance_value   BIGINT,
    PRIMARY KEY (ticker, date),
    CONSTRAINT fk_short_ticker FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── 재무제표 (DART, 분기별) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS financial_statement (
    ticker           VARCHAR(10)  NOT NULL,
    period           VARCHAR(10)  NOT NULL,
    period_type      VARCHAR(5)   NOT NULL,
    revenue          BIGINT,
    operating_income BIGINT,
    net_income       BIGINT,
    total_assets     BIGINT,
    total_equity     BIGINT,
    total_debt       BIGINT,
    cash             BIGINT,
    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, period),
    CONSTRAINT fk_fin_ticker FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── DART 공시 ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dart_disclosure (
    rcept_no     VARCHAR(20)  NOT NULL,
    ticker       VARCHAR(10),
    disclosed_at DATE,
    title        VARCHAR(300),
    category     VARCHAR(50),
    PRIMARY KEY (rcept_no),
    CONSTRAINT fk_disc_ticker FOREIGN KEY (ticker) REFERENCES tickers(ticker) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE INDEX IF NOT EXISTS idx_disc_ticker ON dart_disclosure(ticker);
CREATE INDEX IF NOT EXISTS idx_disc_date   ON dart_disclosure(disclosed_at);

-- ── 거시경제 지표 (ECOS) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS macro_indicator (
    indicator   VARCHAR(50)   NOT NULL,
    date        DATE          NOT NULL,
    `value`     DECIMAL(14,4),
    PRIMARY KEY (indicator, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── 배치 실행 로그 ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS batch_log (
    id            INT          NOT NULL AUTO_INCREMENT,
    batch_name    VARCHAR(50)  NOT NULL,
    started_at    DATETIME     NOT NULL,
    finished_at   DATETIME,
    status        VARCHAR(20)  NOT NULL DEFAULT 'running',
    rows_upserted INT          DEFAULT 0,
    error_msg     TEXT,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
