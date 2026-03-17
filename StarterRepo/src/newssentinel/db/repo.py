from datetime import datetime

from sqlalchemy import String, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .tables import NewsItem
from ..enrich.canonical import build_story_key, canonicalize_url
from ..models.schema import NormalizedItem


def _compute_publication_lag_sec(detected_at: datetime, published_at: datetime | None) -> float | None:
    if not published_at:
        return None
    return (detected_at - published_at).total_seconds()


async def upsert_news_item(session: AsyncSession, item: NormalizedItem) -> NewsItem:
    canonical_url = canonicalize_url(item.url)
    story_key = build_story_key(item.title, item.url)
    publication_lag_sec = _compute_publication_lag_sec(item.detected_at, item.published_at)

    # per-source upsert (source + external_id), while preserving cross-source story_key linkage
    existing = await session.scalar(
        select(NewsItem).where(NewsItem.source == item.source, NewsItem.external_id == item.external_id)
    )
    if existing:
        # keep first detected_at for this source+external_id; update other fields incrementally
        existing.url = item.url or existing.url
        existing.canonical_url = canonical_url or existing.canonical_url
        existing.story_key = story_key
        existing.match_method = "url_title_hash"
        existing.published_at = item.published_at or existing.published_at
        existing.publication_lag_sec = (
            publication_lag_sec if publication_lag_sec is not None else existing.publication_lag_sec
        )
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
        canonical_url=canonical_url,
        story_key=story_key,
        match_method="url_title_hash",
        published_at=item.published_at,
        detected_at=item.detected_at,
        publication_lag_sec=publication_lag_sec,
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
    q = select(NewsItem).order_by(desc(NewsItem.detected_at), desc(NewsItem.id)).limit(limit)
    if source:
        q = q.where(NewsItem.source == source)
    rows = (await session.execute(q)).scalars().all()
    return rows


async def list_latest_dedup(session: AsyncSession, limit: int = 200, source: str | None = None):
    # Coalesce null story keys (legacy rows) to unique IDs to avoid collapsing everything null.
    partition_key = func.coalesce(NewsItem.story_key, cast(NewsItem.id, String))
    ranked = select(
        NewsItem.id.label("id"),
        func.row_number()
        .over(
            partition_by=partition_key,
            order_by=(desc(NewsItem.detected_at), desc(NewsItem.id)),
        )
        .label("rn"),
    )
    if source:
        ranked = ranked.where(NewsItem.source == source)
    ranked_sq = ranked.subquery()

    q = (
        select(NewsItem)
        .join(ranked_sq, NewsItem.id == ranked_sq.c.id)
        .where(ranked_sq.c.rn == 1)
        .order_by(desc(NewsItem.detected_at), desc(NewsItem.id))
        .limit(limit)
    )
    rows = (await session.execute(q)).scalars().all()
    return rows


async def source_lag_metrics(session: AsyncSession, source: str | None = None):
    q = (
        select(
            NewsItem.source.label("source"),
            func.count(NewsItem.id).label("item_count"),
            func.avg(NewsItem.publication_lag_sec).label("avg_publication_lag_sec"),
            func.min(NewsItem.publication_lag_sec).label("min_publication_lag_sec"),
            func.max(NewsItem.publication_lag_sec).label("max_publication_lag_sec"),
        )
        .where(NewsItem.publication_lag_sec.is_not(None))
        .group_by(NewsItem.source)
        .order_by(desc(func.count(NewsItem.id)))
    )
    if source:
        q = q.where(NewsItem.source == source)
    rows = (await session.execute(q)).all()
    return rows
