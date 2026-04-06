from datetime import datetime
from typing import Literal

from fastapi import FastAPI, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.session import get_session
from ..db.repo import list_latest, list_latest_dedup, source_lag_metrics

app = FastAPI(title="NewsSentinel API", version="0.1.0")


def _age_sec(ts: datetime | None, now: datetime) -> float | None:
    if ts is None:
        return None
    return max((now - ts).total_seconds(), 0.0)


def _humanize_age(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} hr ago"
    return f"{int(seconds // 86400)} day ago"


def _live_sort_key(row, now: datetime):
    published_age = _age_sec(row.published_at, now)
    detected_age = _age_sec(row.detected_at, now) or 0.0
    lag = row.publication_lag_sec if row.publication_lag_sec is not None else 10_000_000.0
    # Lower key is better:
    # 1) prefer rows with known published_at
    # 2) fresher published items first
    # 3) lower source lag
    # 4) fresher detection as tie-breaker
    return (
        1 if published_age is None else 0,
        published_age if published_age is not None else 10_000_000.0,
        lag,
        detected_age,
    )

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/news/latest")
async def news_latest(
    limit: int = Query(200, ge=1, le=1000),
    source: str | None = None,
    dedup: bool = True,
    rank_mode: Literal["live", "detected"] = "live",
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await list_latest_dedup(session, limit=limit, source=source)
        if dedup
        else await list_latest(session, limit=limit, source=source)
    )
    now = datetime.utcnow()
    if rank_mode == "live":
        rows = sorted(rows, key=lambda r: _live_sort_key(r, now))
    else:
        rows = sorted(rows, key=lambda r: r.detected_at, reverse=True)
    rows = rows[:limit]

    # return a lean payload for dashboard
    out = []
    for r in rows:
        detected_age_sec = _age_sec(r.detected_at, now)
        published_age_sec = _age_sec(r.published_at, now)
        out.append(
            {
            "id": r.id,
            "source": r.source,
            "source_type": r.source_type,
            "external_id": r.external_id,
            "url": r.url,
            "canonical_url": r.canonical_url,
            "story_key": r.story_key,
            "match_method": r.match_method,
            "published_at": r.published_at,
            "detected_at": r.detected_at,
            "publication_lag_sec": r.publication_lag_sec,
            "detected_age_sec": detected_age_sec,
            "published_age_sec": published_age_sec,
            "detected_recency": _humanize_age(detected_age_sec),
            "published_recency": _humanize_age(published_age_sec),
            "title": r.title,
            "summary": r.summary,
            "tickers": r.tickers,
            "sentiment": r.sentiment,
            "sentiment_model": r.sentiment_model,
        }
        )
    return out


@app.get("/metrics/source-lag")
async def metrics_source_lag(
    source: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    rows = await source_lag_metrics(session, source=source)
    return [
        {
            "source": r.source,
            "item_count": int(r.item_count or 0),
            "avg_publication_lag_sec": float(r.avg_publication_lag_sec) if r.avg_publication_lag_sec is not None else None,
            "min_publication_lag_sec": float(r.min_publication_lag_sec) if r.min_publication_lag_sec is not None else None,
            "max_publication_lag_sec": float(r.max_publication_lag_sec) if r.max_publication_lag_sec is not None else None,
        }
        for r in rows
    ]
