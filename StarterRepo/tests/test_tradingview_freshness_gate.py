import asyncio
from datetime import datetime, timedelta

from newssentinel.collectors.tradingview.collector import TradingViewNewsCollector


def _gmt(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def _html_with_cards(fresh_ts: str, stale_ts: str) -> str:
    return f"""
    <a href="/news/tradingview:fresh-story:0/">
      <article>
        <relative-time event-time="{fresh_ts}"></relative-time>
        <div data-qa-id="news-headline-title">Fresh Story</div>
      </article>
    </a>
    <a href="/news/tradingview:stale-story:0/">
      <article>
        <relative-time event-time="{stale_ts}"></relative-time>
        <div data-qa-id="news-headline-title">Stale Story</div>
      </article>
    </a>
    """


class _FakeClient:
    def __init__(self, html: str):
        self.html = html

    async def get_text(self, _url: str, headers=None):  # pragma: no cover - signature compatibility
        return self.html


def test_tradingview_live_mode_filters_stale_items():
    now = datetime.utcnow()
    html = _html_with_cards(
        fresh_ts=_gmt(now - timedelta(seconds=120)),
        stale_ts=_gmt(now - timedelta(seconds=1800)),
    )
    collector = TradingViewNewsCollector(
        primary_url="https://example.com/news",
        max_items=20,
        live_only=True,
        max_published_age_sec=600,
        include_unknown_published=False,
    )
    collector.client = _FakeClient(html)

    items = asyncio.run(collector.collect())
    assert len(items) == 1
    assert items[0].title == "Fresh Story"


def test_tradingview_backfill_mode_keeps_stale_items():
    now = datetime.utcnow()
    html = _html_with_cards(
        fresh_ts=_gmt(now - timedelta(seconds=120)),
        stale_ts=_gmt(now - timedelta(seconds=1800)),
    )
    collector = TradingViewNewsCollector(
        primary_url="https://example.com/news",
        max_items=20,
        live_only=False,
    )
    collector.client = _FakeClient(html)

    items = asyncio.run(collector.collect())
    titles = sorted([i.title for i in items])
    assert titles == ["Fresh Story", "Stale Story"]
