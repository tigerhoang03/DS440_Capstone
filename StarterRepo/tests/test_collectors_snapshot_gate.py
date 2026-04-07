import asyncio

from newssentinel.collectors.finviz.collector import FinvizNewsCollector
from newssentinel.collectors.tradingview.collector import TradingViewNewsCollector


FINVIZ_HTML = """
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

TRADINGVIEW_HTML = """
<a href="/news/tradingview:abc123:0-sample-story/">
  <article>
    <relative-time event-time="Mon, 16 Mar 2026 07:57:20 GMT"></relative-time>
    <div data-qa-id="news-headline-title">Sample TradingView Headline</div>
  </article>
</a>
"""


class _FakeClient:
    def __init__(self, html: str):
        self.html = html

    async def get_text(self, _url: str, headers=None):  # pragma: no cover - signature compatibility
        return self.html


def test_finviz_snapshot_gate_skips_identical_poll():
    collector = FinvizNewsCollector(url="https://example.com", max_items=10)
    collector.client = _FakeClient(FINVIZ_HTML)

    first = asyncio.run(collector.collect())
    second = asyncio.run(collector.collect())

    assert len(first) == 1
    assert second == []


def test_tradingview_snapshot_gate_skips_identical_poll():
    collector = TradingViewNewsCollector(primary_url="https://example.com/news", max_items=10, live_only=False)
    collector.client = _FakeClient(TRADINGVIEW_HTML)

    first = asyncio.run(collector.collect())
    second = asyncio.run(collector.collect())

    assert len(first) == 1
    assert second == []
