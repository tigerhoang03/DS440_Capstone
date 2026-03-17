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
python -m newssentinel.collectors.run --collector tradingview_news
```

### Run the dashboard
```bash
streamlit run src/newssentinel/dashboard/app.py
```

---

## 2) Project architecture (high level)

```
Collectors (async) --> Redis Streams --> Ingest Worker --> Postgres
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
5. Add **sentiment** model:
   - baseline: VADER (fast) for social
   - upgrade: FinBERT (slower) for news, batched with GPU/ONNX if available

---

## 5) Repo conventions
- `newssentinel/collectors/` contains source-specific collectors
- All collectors output the same `NormalizedItem` schema
- Everything is async-first (httpx, asyncio, async SQLAlchemy)
- Add tests in `tests/` and keep collectors deterministic via fixtures where possible
