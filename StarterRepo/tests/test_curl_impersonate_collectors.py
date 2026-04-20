from datetime import datetime

from newssentinel.collectors.finviz.collector import (
    _build_finviz_external_id,
    _parse_finviz_rows,
    _parse_finviz_time,
)
from newssentinel.collectors.tradingview.collector import _parse_tradingview_cards, _parse_tradingview_time


def test_parse_finviz_rows():
    html = """
    <table>
      <tr class="news_table-row">
        <td class="news_date-cell">6 min</td>
        <td class="news_link-cell">
          <div class="news-badges-container">
            <a class="nn-tab-link" href="/news/123/test-story">Test Headline</a>
            <a class="stock-news-label" href="/quote.ashx?t=TSLA">TSLA</a>
            <span class="news_date-cell">Reuters</span>
          </div>
        </td>
      </tr>
    </table>
    """
    rows = _parse_finviz_rows(html, max_items=10)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://finviz.com/news/123/test-story"
    assert rows[0]["title"] == "Test Headline"
    assert rows[0]["provider"] == "Reuters"
    assert rows[0]["tickers"] == ["TSLA"]


def test_parse_finviz_time_relative():
    now = datetime(2026, 3, 16, 12, 0, 0)
    dt = _parse_finviz_time("6 min", now=now)
    assert dt == datetime(2026, 3, 16, 11, 54, 0)


def test_finviz_external_id_is_stable_for_same_story():
    url = "https://finviz.com/news/123/test-story"
    title = "Test Headline"
    a = _build_finviz_external_id(url=url, title=title)
    b = _build_finviz_external_id(url=url, title=title)
    assert a == b


def test_parse_tradingview_cards():
    html = """
    <a href="/news/top-stories/all/">Top Stories</a>
    <a href="/news/tradingview:abc123:0-sample-story/">
      <article>
        <relative-time event-time="Mon, 16 Mar 2026 07:57:20 GMT"></relative-time>
        <div data-qa-id="news-headline-title">Sample TradingView Headline</div>
      </article>
    </a>
    """
    cards = _parse_tradingview_cards(html, base_url="https://www.tradingview.com", max_items=10)
    assert len(cards) == 1
    assert cards[0]["url"] == "https://www.tradingview.com/news/tradingview:abc123:0-sample-story/"
    assert cards[0]["title"] == "Sample TradingView Headline"
    assert cards[0]["provider"] == "tradingview"


def test_parse_tradingview_time():
    dt = _parse_tradingview_time("Mon, 16 Mar 2026 07:57:20 GMT")
    assert dt is not None
    assert dt.year == 2026
