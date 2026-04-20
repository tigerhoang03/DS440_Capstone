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

- Recommended VSCode extensions
- Python (Microsoft)
- Pylance
- Docker


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

### Run infra
```bash
docker compose up -d
```

### Create DB tables
```bash
python -m newssentinel.scripts.init_db
```

### Run the backend

# Terminal 1: Run the API
- uvicorn newssentinel.api.main:app --reload

# Terminal 2: Run the ingest worker
 - python -m newssentinel.worker.ingest

# Terminal 3: Run the collectors
- python -m newssentinel.collectors.run --collector all_live_news --interval-sec 5

# Terminal 4: Run the Sentiment worker
- python -m newssentinel.worker.sentiment

# Terminal 5: Run the Streamlit dashboard
- streamlit run src/newssentinel/dashboard/app.py

Use `Ctrl+C` to stop loop mode.


READ BELOW:
If dashboard keeps greying in and out or "shadowing" in and out, the streamlit is auto refreshing, complete these steps:

When Streamlit reruns, the page can briefly fade/gray because it is re-rendering the app. On a slower external computer, that effect is more noticeable.

So if everything worked but the dashboard kept pulsing/fading, it is probably not a backend problem. It is the UI refreshing.

What to try:

Increase the refresh interval
- In the sidebar, change refresh from 1s or 2s to something like 5s or 10s.

Turn off auto-refresh
- Toggle Auto-refresh off in the sidebar. The dashboard should stop graying in and out.

Check machine load
- If Docker, collectors, ingest worker, sentiment worker, API, and Streamlit are all running on a weaker laptop, the UI can feel flickery.

If running on a laptop, turn AUTO-REFRESH OFF, or change refresh interval to a higher number than 5 seconds.


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


