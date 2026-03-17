from fastapi import FastAPI, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.session import get_session
from ..db.repo import list_latest, list_latest_dedup, source_lag_metrics

app = FastAPI(title="NewsSentinel API", version="0.1.0")

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/news/latest")
async def news_latest(
    limit: int = Query(200, ge=1, le=1000),
    source: str | None = None,
    dedup: bool = True,
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await list_latest_dedup(session, limit=limit, source=source)
        if dedup
        else await list_latest(session, limit=limit, source=source)
    )
    # return a lean payload for dashboard
    return [
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
            "title": r.title,
            "summary": r.summary,
            "tickers": r.tickers,
            "sentiment": r.sentiment,
            "sentiment_model": r.sentiment_model,
        }
        for r in rows
    ]


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
