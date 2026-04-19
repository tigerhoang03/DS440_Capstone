# NewsSentinel (Capstone Starter)

A Python-first, low-latency platform for **structured news + social sentiment** with a live dashboard.

This starter repo gives you:
- **Async collectors** (RSS, APIs, scraping placeholders) that normalize items into a common schema
- A **FastAPI** backend (ingest + query)
- A **Streamlit** dashboard (live feed, filters, sentiment charts)
- **Postgres** (durable storage) + **Redis Streams** (low-latency queue)
- Docker Compose for local development

> Goal: build toward “Bloomberg-like” speed by using event-driven ingestion, async IO, incremental parsing,
> dedupe, and a fast cache/queue layer.

---

## 1) Quick start (local)

### Prereqs
- Docker Desktop
- Python 3.11+ (3.12 ok)

### Run infra
```bash
docker compose up -d
```

### Create venv & install
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -U pip
pip install -e ".[dev]"
```

### Configure env
Copy `.env.example` to `.env` and edit if needed.

### Create DB tables
```bash
python -m newssentinel.scripts.init_db
```

### Run the backend
```bash
uvicorn newssentinel.api.main:app --reload
```

### Run a collector (RSS demo)
```bash
python -m newssentinel.collectors.run --collector rss_demo
```

### Run the PR Newswire + GlobeNewswire collector
```bash
python -m newssentinel.collectors.run --collector wire_sites_rss
```

### Run the Finviz collector (curl impersonate)
```bash
python -m newssentinel.collectors.run --collector finviz_news
```

### Run the TradingView collector (curl impersonate)
```bash
# live mode (freshness gated)
python -m newssentinel.collectors.run --collector tradingview_news

# optional backfill mode (includes older TradingView items)
python -m newssentinel.collectors.run --collector tradingview_news_backfill
```

### Run all live news collectors in parallel
```bash
python -m newssentinel.collectors.run --collector all_live_news
```

### Run collectors continuously (low-lag mode)
```bash
# all live collectors under one command.
# each source runs independently with its own interval:
# - FINVIZ_NEWS_INTERVAL_SEC (default 2s)
# - TRADINGVIEW_NEWS_INTERVAL_SEC (default 2s)
# - WIRE_SITES_RSS_INTERVAL_SEC (default 5s)
# TradingView live freshness gate:
# - TRADINGVIEW_LIVE_MAX_PUBLISHED_AGE_SEC (default 600s)
# - TRADINGVIEW_LIVE_MAX_ITEMS (default 40)
# - TRADINGVIEW_LIVE_INCLUDE_UNKNOWN_PUBLISHED (default false)
# stateful delta cache is persisted across restarts by default:
# - COLLECTOR_STATE_ENABLED=true
# - COLLECTOR_STATE_DIR=.collector_state
# --interval-sec acts as fallback for any source without a specific interval env var.
python -m newssentinel.collectors.run --collector all_live_news --interval-sec 5

# single collector every 10 seconds
python -m newssentinel.collectors.run --collector finviz_news --interval-sec 10
```

Use `Ctrl+C` to stop loop mode.

### Run the dashboard
```bash
streamlit run src/newssentinel/dashboard/app.py
```

### Run FinBERT sentiment enrichment
```bash
# Run in its own terminal after the ingest worker is running.
# This scores article titles only and updates Postgres asynchronously.
python -m newssentinel.worker.sentiment

# Optional one-cycle smoke test
python -m newssentinel.worker.sentiment --once
```

### Prepare and score the Financial PhraseBank benchmark
```bash
python -m newssentinel.scripts.prepare_sentiment_benchmark
python -m newssentinel.scripts.score_sentiment_benchmark
```

Generated benchmark files are written under `artifacts/sentiment/` and are intentionally ignored by git.

---

## 2) Project architecture (high level)

```
Collectors (async) --> Redis Streams --> Ingest Worker --> Postgres
                                                 |
                                                 v
                                      FinBERT Sentiment Worker
                                                 |
                                                 v
                                           FastAPI Query
                                                 |
                                                 v
                                           Streamlit UI
```

**Why Redis Streams?**
- very low latency fan-in
- decouples collectors from storage
- supports backpressure and replay for debugging

**Why Postgres?**
- reliable, queryable, easy to add indexes
- can upgrade to TimescaleDB later for time-series heavy analytics

---

## 3) Where your professor's requirements fit

### Structured
- RSS from official URLs -> `collectors/rss/*`
- FreshRSS DB exposure -> `connectors/freshrss/*` (read their MySQL/SQLite)
- RSSGuard DB exposure -> `connectors/rssguard/*` (read their SQLite)
- FinViz (API + scraping) -> `collectors/finviz/*`
- TradingView news alerts -> adapter stub in `collectors/tradingview/*`
- OCR pipeline -> `ocr/*` (placeholder; integrate later)

### Social
- StockTwits -> `collectors/stocktwits/*` (HTTP async, with anti-rate-limit behavior)
- TD Ameritrade social sentiment -> adapter stub
- Reddit / X(Twitter) -> stubs ready for expansion

### Broker feeds
- IBKR news -> `collectors/ibkr/*` (integration stub; plug in provided code)
- TD Ameritrade news -> `collectors/tda/*` (integration stub)

---

## 4) Next steps (recommended)
1. Confirm which data sources you can **legally** access and what rate limits apply.
2. Get **FreshRSS** and/or **RSSGuard** running locally; implement DB readers.
3. Plug in **IBKR** and **TDA** code you already have into the adapter skeletons.
4. Add **dedupe** rules + tickers extraction + per-ticker streams.
5. Continue improving **sentiment**:
   - current: VADER fallback in collectors + async FinBERT title scoring worker
   - next: tune thresholds, compare benchmark metrics, and consider GPU/ONNX batching

---

## 5) Repo conventions
- `newssentinel/collectors/` contains source-specific collectors
- All collectors output the same `NormalizedItem` schema
- Everything is async-first (httpx, asyncio, async SQLAlchemy)
- Add tests in `tests/` and keep collectors deterministic via fixtures where possible
