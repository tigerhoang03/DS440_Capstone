from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from .tables import NewsItem
from ..models.schema import NormalizedItem

async def upsert_news_item(session: AsyncSession, item: NormalizedItem) -> NewsItem:
    # naive upsert: try insert; on conflict handled by unique constraint via merge pattern
    existing = await session.scalar(
        select(NewsItem).where(NewsItem.source == item.source, NewsItem.external_id == item.external_id)
    )
    if existing:
        # update minimal fields (keep detected_at first time for latency studies? you can choose)
        existing.url = item.url or existing.url
        existing.published_at = item.published_at or existing.published_at
        existing.title = item.title or existing.title
        existing.summary = item.summary or existing.summary
        existing.content = item.content or existing.content
        existing.tickers = item.tickers or existing.tickers
        existing.sentiment = item.sentiment if item.sentiment is not None else existing.sentiment
        existing.sentiment_model = item.sentiment_model or existing.sentiment_model
        existing.raw = {**(existing.raw or {}), **(item.raw or {})}
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing

    row = NewsItem(
        source=item.source,
        source_type=item.source_type.value,
        external_id=item.external_id,
        url=item.url,
        published_at=item.published_at,
        detected_at=item.detected_at,
        title=item.title,
        summary=item.summary,
        content=item.content,
        tickers=item.tickers,
        author=item.author,
        language=item.language,
        sentiment=item.sentiment,
        sentiment_model=item.sentiment_model,
        raw=item.raw,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row

async def list_latest(session: AsyncSession, limit: int = 200, source: str | None = None):
    q = select(NewsItem).order_by(desc(NewsItem.detected_at)).limit(limit)
    if source:
        q = q.where(NewsItem.source == source)
    rows = (await session.execute(q)).scalars().all()
    return rows
