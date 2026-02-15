from fastapi import FastAPI, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.session import get_session
from ..db.repo import list_latest

app = FastAPI(title="NewsSentinel API", version="0.1.0")

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/news/latest")
async def news_latest(
    limit: int = Query(200, ge=1, le=1000),
    source: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    rows = await list_latest(session, limit=limit, source=source)
    # return a lean payload for dashboard
    return [
        {
            "id": r.id,
            "source": r.source,
            "source_type": r.source_type,
            "external_id": r.external_id,
            "url": r.url,
            "published_at": r.published_at,
            "detected_at": r.detected_at,
            "title": r.title,
            "summary": r.summary,
            "tickers": r.tickers,
            "sentiment": r.sentiment,
            "sentiment_model": r.sentiment_model,
        }
        for r in rows
    ]
