# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**StockLens** is a Korean stock market analysis platform. It aggregates data from Korean financial APIs (pykrx, DART, ECOS), stores it in PostgreSQL, and serves a vanilla JS SPA with charts and dashboards.

## Running the Project

```bash
# Start all services (recommended)
docker-compose up -d

# View logs
docker-compose logs -f backend

# Run locally without Docker
pip install -r requirements.txt
cd backend && python app.py
```

## Batch Data Collection

```bash
# Run daily collector once (post-market: OHLCV, fundamentals, investor trading)
cd backend && python -m batch.daily_collector

# Run with built-in scheduler (triggers daily ~16:30 KST)
cd backend && python -m batch.daily_collector --schedule

# Run DART financial statement collector
cd backend && python -m batch.dart_collector
```

## Architecture

```
Frontend (Vanilla JS SPA, port 5001)
    ↓ HTTP/JSON via api.js (3-retry logic)
Backend (Flask REST API, port 5001)
    ↓ SQLAlchemy 2.0
PostgreSQL 16
    ↓ fallback when DB empty
pykrx / DART API / ECOS API
```

**Backend is organized into three layers:**
- `api/` — Flask blueprints (market, stocks, analysis, recommendations)
- `services/` — Business logic; each service owns its caching and fallback strategy
- `db/` — SQLAlchemy models, session factory, and repository queries

**Caching strategy (per request):**
1. In-memory TTL cache (300s for OHLCV, up to 6h for statics)
2. PostgreSQL (persistent, populated by batch jobs)
3. Live API calls (pykrx/DART/ECOS) as last resort

**KRX session:** Authenticated once at startup; the session is monkey-patched into pykrx so it persists across requests (`krx_session/manager.py`).

**Frontend** is a no-build SPA using ES6 modules: `router.js` handles client-side routing, `store.js` manages state, and `views/` contains page components. Chart.js with `chartjs-chart-financial` powers the candlestick/line charts.

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|---|---|
| `KRX_LOGIN_ID` / `KRX_LOGIN_PW` | data.krx.co.kr credentials |
| `DART_API_KEY` | opendart.fss.or.kr API key |
| `ECOS_API_KEY` | Bank of Korea ECOS API key |
| `DATABASE_URL` | PostgreSQL connection string |
| `FLASK_PORT` | Default: 5001 |
| `SECRET_KEY` | Flask session secret |

## Database

Schema is initialized from `db/init.sql`. Key tables:
- `tickers` — master list; all other tables FK to this with CASCADE DELETE
- `daily_ohlcv`, `daily_fundamental`, `daily_market_cap` — daily price/valuation data
- `daily_investor_trading`, `daily_shorting` — trading flow data
- `financial_statement` — DART quarterly/annual financials
- `macro_indicator` — ECOS macro data (base rate, USD/KRW, CPI)
- `batch_log` — batch job execution history

Composite PKs are `(ticker, date)`. Connection pool: size=10, max_overflow=20.

## Key Conventions

- Comments and commit messages are written in Korean.
- Services return pandas DataFrames internally; `utils/serializers.py` converts them to JSON for API responses.
- `config.py` is the single source of truth for all env vars and TTL constants — add new config there, not inline.
- Flask serves the frontend via a catch-all route (`/`), so the backend and frontend share the same port.
