from datetime import datetime

from sqlalchemy import String, cast, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .tables import NewsItem
from ..enrich.canonical import build_story_key, canonicalize_url
from ..models.schema import NormalizedItem


def _compute_publication_lag_sec(detected_at: datetime, published_at: datetime | None) -> float | None:
    if not published_at:
        return None
    return (detected_at - published_at).total_seconds()


def build_news_row_data(item: NormalizedItem) -> dict:
    canonical_url = canonicalize_url(item.url)
    story_key = build_story_key(item.title, item.url)
    publication_lag_sec = _compute_publication_lag_sec(item.detected_at, item.published_at)
    return {
        "source": item.source,
        "source_type": item.source_type.value,
        "external_id": item.external_id,
        "url": item.url,
        "canonical_url": canonical_url,
        "story_key": story_key,
        "match_method": "url_title_hash",
        "published_at": item.published_at,
        "detected_at": item.detected_at,
        "publication_lag_sec": publication_lag_sec,
        "title": item.title,
        "summary": item.summary,
        "content": item.content,
        "tickers": item.tickers,
        "author": item.author,
        "language": item.language,
        "sentiment": item.sentiment,
        "sentiment_model": item.sentiment_model,
        "raw": item.raw,
    }


async def upsert_news_items(session: AsyncSession, items: list[NormalizedItem]) -> int:
    if not items:
        return 0

    rows = [build_news_row_data(item) for item in items]
    stmt = pg_insert(NewsItem).values(rows)
    excluded = stmt.excluded

    upsert_stmt = stmt.on_conflict_do_update(
        constraint="uq_source_external_id",
        set_={
            "source_type": excluded.source_type,
            # Keep first detected_at for source/external_id; update mutable fields.
            "url": func.coalesce(excluded.url, NewsItem.url),
            "canonical_url": func.coalesce(excluded.canonical_url, NewsItem.canonical_url),
            "story_key": excluded.story_key,
            "match_method": excluded.match_method,
            "published_at": func.coalesce(excluded.published_at, NewsItem.published_at),
            "publication_lag_sec": func.coalesce(excluded.publication_lag_sec, NewsItem.publication_lag_sec),
            "title": func.coalesce(excluded.title, NewsItem.title),
            "summary": func.coalesce(excluded.summary, NewsItem.summary),
            "content": func.coalesce(excluded.content, NewsItem.content),
            "tickers": func.coalesce(excluded.tickers, NewsItem.tickers),
            "author": func.coalesce(excluded.author, NewsItem.author),
            "language": func.coalesce(excluded.language, NewsItem.language),
            "sentiment": func.coalesce(excluded.sentiment, NewsItem.sentiment),
            "sentiment_model": func.coalesce(excluded.sentiment_model, NewsItem.sentiment_model),
            "raw": func.coalesce(excluded.raw, NewsItem.raw),
        },
    )
    await session.execute(upsert_stmt)
    return len(items)


async def upsert_news_item(session: AsyncSession, item: NormalizedItem) -> NewsItem:
    # Compatibility wrapper for one-off calls.
    await upsert_news_items(session, [item])
    await session.commit()
    row = await session.scalar(
        select(NewsItem).where(NewsItem.source == item.source, NewsItem.external_id == item.external_id)
    )
    if row is None:
        raise RuntimeError("Upsert did not persist row")
    return row

async def list_latest(session: AsyncSession, limit: int = 200, source: str | None = None):
    q = select(NewsItem).order_by(desc(NewsItem.detected_at), desc(NewsItem.id)).limit(limit)
    if source:
        q = q.where(NewsItem.source == source)
    rows = (await session.execute(q)).scalars().all()
    return rows


def _filtered_news_select(
    source: str | None = None,
    detected_after: datetime | None = None,
    detected_before: datetime | None = None,
):
    stmt = select(NewsItem)
    if source:
        stmt = stmt.where(NewsItem.source == source)
    if detected_after:
        stmt = stmt.where(NewsItem.detected_at >= detected_after)
    if detected_before:
        stmt = stmt.where(NewsItem.detected_at < detected_before)
    return stmt


async def list_latest_dedup(session: AsyncSession, limit: int = 200, source: str | None = None):
    return await list_news_filtered(session, limit=limit, source=source, dedup=True)


async def list_news_filtered(
    session: AsyncSession,
    limit: int = 200,
    source: str | None = None,
    detected_after: datetime | None = None,
    detected_before: datetime | None = None,
    dedup: bool = True,
):
    base_stmt = _filtered_news_select(
        source=source,
        detected_after=detected_after,
        detected_before=detected_before,
    )

    if not dedup:
        stmt = base_stmt.order_by(desc(NewsItem.detected_at), desc(NewsItem.id)).limit(limit)
        return (await session.execute(stmt)).scalars().all()

    filtered_sq = base_stmt.subquery()
    partition_key = func.coalesce(filtered_sq.c.story_key, cast(filtered_sq.c.id, String))
    ranked_sq = (
        select(
            filtered_sq.c.id.label("id"),
            func.row_number()
            .over(
                partition_by=partition_key,
                order_by=(desc(filtered_sq.c.detected_at), desc(filtered_sq.c.id)),
            )
            .label("rn"),
        )
        .subquery()
    )

    stmt = (
        select(NewsItem)
        .join(ranked_sq, NewsItem.id == ranked_sq.c.id)
        .where(ranked_sq.c.rn == 1)
        .order_by(desc(NewsItem.detected_at), desc(NewsItem.id))
        .limit(limit)
    )
    return (await session.execute(stmt)).scalars().all()


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
