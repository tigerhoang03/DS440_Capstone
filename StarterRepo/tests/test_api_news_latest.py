from datetime import datetime, timedelta
from types import SimpleNamespace

from newssentinel.api import main


def _row(
    item_id: int,
    *,
    detected_at: datetime,
    published_at: datetime | None = None,
    source: str = "finviz_news",
    title: str = "Headline",
    summary: str | None = None,
    tickers: list[str] | None = None,
    sentiment_model: str | None = "vader",
    raw: dict | None = None,
):
    return SimpleNamespace(
        id=item_id,
        source=source,
        source_type="scrape",
        external_id=f"ext-{item_id}",
        url=f"https://example.com/{item_id}",
        canonical_url=f"https://example.com/{item_id}",
        story_key=f"story-{item_id}",
        match_method="url_title_hash",
        published_at=published_at,
        detected_at=detected_at,
        publication_lag_sec=(detected_at - published_at).total_seconds() if published_at else None,
        title=title,
        summary=summary,
        tickers=tickers or [],
        sentiment=0.1,
        sentiment_model=sentiment_model,
        raw=raw or {},
    )


async def test_news_latest_detected_after_filters_rows(monkeypatch):
    now = datetime(2026, 4, 13, 14, 0, 0)
    rows = [
        _row(1, detected_at=now - timedelta(minutes=5)),
        _row(2, detected_at=now + timedelta(minutes=1)),
    ]

    async def fake_list_news_filtered(*args, **kwargs):
        return rows

    monkeypatch.setattr(main, "list_news_filtered", fake_list_news_filtered)
    out = await main.news_latest(limit=200, detected_after=now, session=object())

    assert [item["id"] for item in out] == [2]


async def test_news_latest_detected_before_filters_rows(monkeypatch):
    now = datetime(2026, 4, 13, 14, 0, 0)
    rows = [
        _row(1, detected_at=now - timedelta(minutes=5)),
        _row(2, detected_at=now + timedelta(minutes=1)),
    ]

    async def fake_list_news_filtered(*args, **kwargs):
        return rows

    monkeypatch.setattr(main, "list_news_filtered", fake_list_news_filtered)
    out = await main.news_latest(limit=200, detected_before=now, session=object())

    assert [item["id"] for item in out] == [1]


async def test_news_latest_ticker_query_ranks_exact_ticker_before_text(monkeypatch):
    now = datetime(2026, 4, 13, 14, 0, 0)
    rows = [
        _row(1, detected_at=now, title="Tesla shares climb", tickers=["TSLA"]),
        _row(2, detected_at=now, title="TSLA mentioned in macro roundup", tickers=[]),
    ]

    async def fake_list_news_filtered(*args, **kwargs):
        return rows

    monkeypatch.setattr(main, "list_news_filtered", fake_list_news_filtered)
    out = await main.news_latest(limit=200, q="TSLA", session=object())

    assert [item["id"] for item in out] == [1, 2]


async def test_news_latest_text_query_searches_title_summary_and_source(monkeypatch):
    now = datetime(2026, 4, 13, 14, 0, 0)
    rows = [
        _row(1, detected_at=now, title="Fed signals caution"),
        _row(2, detected_at=now - timedelta(seconds=1), summary="The fed remains data dependent"),
        _row(3, detected_at=now - timedelta(seconds=2), source="fedwire_news"),
    ]

    async def fake_list_news_filtered(*args, **kwargs):
        return rows

    monkeypatch.setattr(main, "list_news_filtered", fake_list_news_filtered)
    out = await main.news_latest(limit=200, q="fed", session=object())

    assert [item["id"] for item in out] == [1, 2, 3]


async def test_news_latest_headline_keyword_matches_title_case_insensitively(monkeypatch):
    now = datetime(2026, 4, 13, 14, 0, 0)
    rows = [
        _row(1, detected_at=now, title="Apple revenue tops estimates", tickers=[]),
        _row(2, detected_at=now - timedelta(seconds=1), title="APPLE launches new product", tickers=[]),
        _row(3, detected_at=now - timedelta(seconds=2), title="Different story", summary="Revenue note"),
    ]

    async def fake_list_news_filtered(*args, **kwargs):
        return rows

    monkeypatch.setattr(main, "list_news_filtered", fake_list_news_filtered)
    out = await main.news_latest(limit=200, headline_keyword="apple", session=object())

    assert [item["id"] for item in out] == [1, 2]


async def test_news_latest_ticker_and_headline_keyword_are_combined(monkeypatch):
    now = datetime(2026, 4, 13, 14, 0, 0)
    rows = [
        _row(1, detected_at=now, title="Tesla revenue tops estimates", tickers=["TSLA"]),
        _row(2, detected_at=now - timedelta(seconds=1), title="Tesla guidance update", tickers=["TSLA"]),
        _row(3, detected_at=now - timedelta(seconds=2), title="Revenue beats at Ford", tickers=["F"]),
    ]

    async def fake_list_news_filtered(*args, **kwargs):
        return rows

    monkeypatch.setattr(main, "list_news_filtered", fake_list_news_filtered)
    out = await main.news_latest(
        limit=200,
        tickers="TSLA",
        headline_keyword="revenue",
        session=object(),
    )

    assert [item["id"] for item in out] == [1]


async def test_news_latest_search_stays_within_requested_recent_window(monkeypatch):
    now = datetime(2026, 4, 13, 14, 0, 0)
    seen = {}

    async def fake_list_news_filtered(*args, **kwargs):
        seen["limit"] = kwargs["limit"]
        return [
            _row(1, detected_at=now, title="Recent revenue headline", tickers=["TSLA"]),
        ]

    monkeypatch.setattr(main, "list_news_filtered", fake_list_news_filtered)
    out = await main.news_latest(limit=50, tickers="TSLA", headline_keyword="revenue", session=object())

    assert seen["limit"] == 50
    assert [item["id"] for item in out] == [1]


async def test_news_latest_passes_dedup_flag_to_repo(monkeypatch):
    seen = {}

    async def fake_list_news_filtered(*args, **kwargs):
        seen["dedup"] = kwargs["dedup"]
        return []

    monkeypatch.setattr(main, "list_news_filtered", fake_list_news_filtered)
    await main.news_latest(limit=200, dedup=False, session=object())

    assert seen["dedup"] is False


async def test_news_latest_returns_finbert_sentiment_label(monkeypatch):
    now = datetime(2026, 4, 13, 14, 0, 0)
    rows = [
        _row(
            1,
            detected_at=now,
            sentiment_model="finbert",
            raw={"sentiment_finbert": {"label": "positive"}},
        )
    ]

    async def fake_list_news_filtered(*args, **kwargs):
        return rows

    monkeypatch.setattr(main, "list_news_filtered", fake_list_news_filtered)
    out = await main.news_latest(limit=200, session=object())

    assert out[0]["sentiment_label"] == "positive"
