# FinViz collector (placeholder)

You will likely implement two paths:
1) "API-like" endpoints / paid data if provided
2) HTML scraping of FinViz news table

Guidance:
- Use `httpx` with caching and backoff.
- Parse news rows into NormalizedItem.
- IMPORTANT: do NOT hammer requests. Use adaptive scheduling.

Add:
- `scrape_news.py`
- `portfolio_alerts.py`
