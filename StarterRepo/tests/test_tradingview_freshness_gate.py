import asyncio
from datetime import datetime, timedelta

from newssentinel.collectors.tradingview.collector import (
    TradingViewNewsCollector,
    _filter_gated_cards,
    _is_gated_tradingview_title,
    _parse_tradingview_api_items,
)


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
    def __init__(
        self,
        html: str | dict[str, str],
        json_data: dict | Exception | None = None,
    ):
        self.html = html
        self.json_data = json_data
        self.calls: list[str] = []
        self.json_calls: list[str] = []

    async def get_json(self, url: str, params=None, headers=None):  # pragma: no cover - signature compatibility
        self.json_calls.append(url)
        if isinstance(self.json_data, Exception):
            raise self.json_data
        if self.json_data is None:
            raise RuntimeError("No fake JSON configured")
        return self.json_data

    async def get_text(self, _url: str, headers=None):  # pragma: no cover - signature compatibility
        self.calls.append(_url)
        if isinstance(self.html, dict):
            return self.html[_url]
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


def test_tradingview_gated_title_detection():
    assert _is_gated_tradingview_title("Sign in to read exclusive news")
    assert _is_gated_tradingview_title("Please sign in to see news")
    assert not _is_gated_tradingview_title("NVDA stock rises after earnings beat")


def test_tradingview_gated_cards_are_filtered():
    cards, skipped = _filter_gated_cards(
        [
            {"title": "Sign in to read exclusive news"},
            {"title": "Please sign in to see news"},
            {"title": "NVDA stock rises after earnings beat"},
        ]
    )

    assert skipped == 2
    assert cards == [{"title": "NVDA stock rises after earnings beat"}]


def test_parse_tradingview_api_items_normalizes_live_json():
    published = 1776628996
    cards = _parse_tradingview_api_items(
        {
            "items": [
                {
                    "id": "tradingview:abc123:0",
                    "title": "MSTR: Bitcoin treasury update",
                    "published": published,
                    "storyPath": "/news/tradingview:abc123:0-bitcoin-treasury-update/",
                    "provider": {"id": "tradingview", "name": "TradingView"},
                    "relatedSymbols": [{"symbol": "NASDAQ:MSTR"}],
                }
            ]
        },
        max_items=10,
    )

    assert cards == [
        {
            "api_id": "tradingview:abc123:0",
            "url": "https://www.tradingview.com/news/tradingview:abc123:0-bitcoin-treasury-update/",
            "title": "MSTR: Bitcoin treasury update",
            "raw_event_time": "2026-04-19T20:03:16",
            "provider": "TradingView",
            "provider_id": "tradingview",
            "tickers": ["MSTR"],
            "collector": "tradingview_mediator_api",
        }
    ]


def test_tradingview_api_results_are_used_before_html():
    now = datetime.utcnow()
    collector = TradingViewNewsCollector(
        primary_url="https://example.com/news-flow",
        fallback_url="https://example.com/news",
        api_url="https://example.com/api",
        max_items=20,
        live_only=True,
        max_published_age_sec=600,
        include_unknown_published=False,
    )
    fake_client = _FakeClient(
        html="",
        json_data={
            "items": [
                {
                    "id": "tradingview:fresh-api-story:0",
                    "title": "AAPL: Fresh API Story",
                    "published": int((now - timedelta(seconds=60)).timestamp()),
                    "link": "https://example.com/story",
                    "provider": {"id": "tradingview", "name": "TradingView"},
                    "relatedSymbols": [{"symbol": "NASDAQ:AAPL"}],
                }
            ]
        },
    )
    collector.client = fake_client

    items = asyncio.run(collector.collect())

    assert len(items) == 1
    assert items[0].external_id == "tradingview:fresh-api-story:0"
    assert items[0].title == "AAPL: Fresh API Story"
    assert items[0].url == "https://example.com/story"
    assert items[0].tickers == ["AAPL"]
    assert items[0].raw["collector"] == "tradingview_mediator_api"
    assert fake_client.json_calls == ["https://example.com/api"]
    assert fake_client.calls == []


def test_tradingview_api_gated_items_are_skipped():
    now = datetime.utcnow()
    collector = TradingViewNewsCollector(
        api_url="https://example.com/api",
        max_items=20,
        live_only=True,
        max_published_age_sec=600,
        include_unknown_published=False,
    )
    collector.client = _FakeClient(
        html="",
        json_data={
            "items": [
                {
                    "id": "dow-jones:gated:0",
                    "title": "Please sign in to see news",
                    "published": int((now - timedelta(seconds=60)).timestamp()),
                    "storyPath": "/news/dow-jones:gated:0/",
                    "provider": {"id": "dow-jones", "name": "Dow Jones Newswires"},
                }
            ]
        },
    )

    assert asyncio.run(collector.collect()) == []


def test_tradingview_html_fallback_used_when_api_fails():
    now = datetime.utcnow()
    primary_url = "https://example.com/news-flow"
    collector = TradingViewNewsCollector(
        primary_url=primary_url,
        fallback_url="https://example.com/news",
        api_url="https://example.com/api",
        max_items=20,
        live_only=True,
        max_published_age_sec=600,
        include_unknown_published=False,
    )
    fake_client = _FakeClient(
        html={primary_url: _html_with_cards(_gmt(now - timedelta(seconds=60)), _gmt(now - timedelta(seconds=1800)))},
        json_data=RuntimeError("API down"),
    )
    collector.client = fake_client

    items = asyncio.run(collector.collect())

    assert [item.title for item in items] == ["Fresh Story"]
    assert fake_client.json_calls == ["https://example.com/api"]
    assert fake_client.calls == [primary_url]


def test_tradingview_fallback_used_when_primary_is_gated():
    now = datetime.utcnow()
    primary_url = "https://example.com/news-flow"
    fallback_url = "https://example.com/news"
    primary_html = f"""
    <a href="/news/dow-jones:exclusive:0/">
      <article>
        <relative-time event-time="{_gmt(now - timedelta(seconds=60))}"></relative-time>
        <div data-qa-id="news-headline-title">Sign in to read exclusive news</div>
      </article>
    </a>
    """
    fallback_html = _html_with_cards(
        fresh_ts=_gmt(now - timedelta(seconds=120)),
        stale_ts=_gmt(now - timedelta(seconds=1800)),
    )
    collector = TradingViewNewsCollector(
        primary_url=primary_url,
        fallback_url=fallback_url,
        max_items=20,
        live_only=True,
        max_published_age_sec=600,
        include_unknown_published=False,
    )
    fake_client = _FakeClient({primary_url: primary_html, fallback_url: fallback_html})
    collector.client = fake_client

    items = asyncio.run(collector.collect())

    assert [item.title for item in items] == ["Fresh Story"]
    assert fake_client.calls == [primary_url, fallback_url]


def test_tradingview_fallback_not_used_when_primary_has_usable_cards():
    now = datetime.utcnow()
    primary_url = "https://example.com/news-flow"
    fallback_url = "https://example.com/news"
    collector = TradingViewNewsCollector(
        primary_url=primary_url,
        fallback_url=fallback_url,
        max_items=20,
        live_only=True,
        max_published_age_sec=600,
        include_unknown_published=False,
    )
    fake_client = _FakeClient(
        {
            primary_url: _html_with_cards(
                fresh_ts=_gmt(now - timedelta(seconds=120)),
                stale_ts=_gmt(now - timedelta(seconds=1800)),
            ),
            fallback_url: "",
        }
    )
    collector.client = fake_client

    items = asyncio.run(collector.collect())

    assert [item.title for item in items] == ["Fresh Story"]
    assert fake_client.calls == [primary_url]


def test_tradingview_repeated_gated_cycles_reset_session(monkeypatch):
    now = datetime.utcnow()
    primary_html = f"""
    <a href="/news/dow-jones:exclusive:0/">
      <article>
        <relative-time event-time="{_gmt(now - timedelta(seconds=60))}"></relative-time>
        <div data-qa-id="news-headline-title">Sign in to read exclusive news</div>
      </article>
    </a>
    """
    collector = TradingViewNewsCollector(
        primary_url="https://example.com/news-flow",
        fallback_url="https://example.com/news",
        max_items=20,
        live_only=True,
        max_published_age_sec=600,
        include_unknown_published=False,
    )
    monkeypatch.setattr(
        "newssentinel.collectors.tradingview.collector.settings.TRADINGVIEW_GATED_SESSION_RESET_THRESHOLD",
        2,
    )
    collector.client = _FakeClient(
        {
            "https://example.com/news-flow": primary_html,
            "https://example.com/news": "",
        }
    )
    resets = 0

    def fake_reset_client():
        nonlocal resets
        resets += 1

    collector._reset_client = fake_reset_client

    assert asyncio.run(collector.collect()) == []
    assert asyncio.run(collector.collect()) == []
    assert resets == 1
