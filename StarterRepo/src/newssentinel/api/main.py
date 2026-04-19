from datetime import datetime
from typing import Literal

from fastapi import FastAPI, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.session import get_session
from ..db.repo import list_news_filtered, source_lag_metrics

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


def _parse_tickers_param(tickers: str | None) -> list[str]:
    if not tickers:
        return []
    out = []
    for token in tickers.split(","):
        normalized = token.strip().upper()
        if normalized:
            out.append(normalized)
    return out


def _looks_like_ticker(token: str | None) -> str | None:
    if not token:
        return None
    normalized = token.strip().upper()
    if not normalized:
        return None
    candidate = normalized.replace(".", "").replace("-", "")
    if 1 <= len(normalized) <= 8 and candidate.isalnum():
        return normalized
    return None


def _string_match(value: str | None, needle: str) -> bool:
    return bool(value and needle in value.lower())


def _row_matches_filters(
    row,
    q: str | None,
    tickers: list[str],
    headline_keyword: str | None,
    detected_after: datetime | None,
    detected_before: datetime | None,
) -> bool:
    if detected_after is not None and row.detected_at < detected_after:
        return False
    if detected_before is not None and row.detected_at >= detected_before:
        return False
    row_tickers = {ticker.upper() for ticker in (row.tickers or [])}
    if tickers and not any(ticker in row_tickers for ticker in tickers):
        return False
    if headline_keyword:
        title = (row.title or "").lower()
        if headline_keyword.lower() not in title:
            return False
    if not q:
        return True
    q_lower = q.lower()
    q_ticker = _looks_like_ticker(q)
    return any(
        [
            q_ticker is not None and q_ticker in row_tickers,
            _string_match(row.title, q_lower),
            _string_match(row.summary, q_lower),
            _string_match(row.source, q_lower),
        ]
    )


def _detected_sort_key(row):
    return (row.detected_at, row.id)


def _search_sort_key(row, now: datetime, q: str | None, tickers: list[str], rank_mode: str):
    row_tickers = {ticker.upper() for ticker in (row.tickers or [])}
    q_lower = (q or "").strip().lower()
    q_ticker = _looks_like_ticker(q)

    ticker_rank = 0 if (tickers and any(ticker in row_tickers for ticker in tickers)) else 1
    if not tickers:
        ticker_rank = 0 if (q_ticker and q_ticker in row_tickers) else 1

    title_rank = 0 if q_lower and _string_match(row.title, q_lower) else 1
    summary_rank = 0 if q_lower and _string_match(row.summary, q_lower) else 1
    source_rank = 0 if q_lower and _string_match(row.source, q_lower) else 1

    base_rank = _live_sort_key(row, now) if rank_mode == "live" else (
        0,
        0,
        0,
        -row.detected_at.timestamp(),
    )
    return (
        ticker_rank,
        title_rank,
        summary_rank,
        source_rank,
        *base_rank,
    )


def _sentiment_label(row) -> str | None:
    raw = getattr(row, "raw", None) or {}
    finbert = raw.get("sentiment_finbert") if isinstance(raw, dict) else None
    if isinstance(finbert, dict):
        label = finbert.get("label")
        if label:
            return str(label)
    return None


@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/news/latest")
async def news_latest(
    limit: int = Query(200, ge=1, le=1000),
    source: str | None = None,
    q: str | None = None,
    tickers: str | None = None,
    headline_keyword: str | None = None,
    detected_after: datetime | None = None,
    detected_before: datetime | None = None,
    dedup: bool = True,
    rank_mode: Literal["live", "detected"] = "live",
    session: AsyncSession = Depends(get_session),
):
    ticker_filters = _parse_tickers_param(tickers)
    rows = await list_news_filtered(
        session,
        limit=limit,
        source=source,
        detected_after=detected_after,
        detected_before=detected_before,
        dedup=dedup,
    )
    now = datetime.utcnow()
    rows = [
        row for row in rows
        if _row_matches_filters(
            row=row,
            q=q,
            tickers=ticker_filters,
            headline_keyword=headline_keyword,
            detected_after=detected_after,
            detected_before=detected_before,
        )
    ]
    if q or ticker_filters or headline_keyword:
        rows = sorted(rows, key=lambda r: _search_sort_key(r, now, q, ticker_filters, rank_mode))
    elif rank_mode == "live":
        rows = sorted(rows, key=lambda r: _live_sort_key(r, now))
    else:
        rows = sorted(rows, key=_detected_sort_key, reverse=True)
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
            "sentiment_label": _sentiment_label(r),
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
