from __future__ import annotations

from datetime import datetime
import hashlib
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from ..base import Collector
from ...config import settings
from ...enrich.sentiment import vader_compound
from ...enrich.tickers import extract_tickers
from ...http.impersonate import ImpersonateHttpClient
from ...models.schema import NormalizedItem, SourceType

_ARTICLE_LINK_RE = re.compile(r"^/news/[a-z0-9_-]+:[^/]+/", re.IGNORECASE)


def _parse_tradingview_cards(html: str, base_url: str, max_items: int = 100):
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    out: list[dict] = []

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not _ARTICLE_LINK_RE.match(href):
            continue
        full_url = urljoin(base_url, href)
        if full_url in seen:
            continue
        seen.add(full_url)

        title_node = a.select_one("[data-qa-id='news-headline-title']")
        title = title_node.get_text(" ", strip=True) if title_node else None
        if not title:
            text = a.get_text(" ", strip=True)
            # link text usually starts with "16 hours ago TradingView ..."
            title = text.split(" TradingView ", 1)[-1] if " TradingView " in text else text
        title = (title or "").strip()
        if not title:
            continue

        rel_node = a.select_one("relative-time[event-time]")
        raw_event_time = rel_node.get("event-time") if rel_node else None
        if not raw_event_time:
            time_node = a.select_one("time[datetime]")
            raw_event_time = time_node.get("datetime") if time_node else None

        provider = None
        m = re.match(r"^/news/([a-z0-9_-]+):", href, flags=re.IGNORECASE)
        if m:
            provider = m.group(1)

        out.append(
            {
                "url": full_url,
                "title": title,
                "raw_event_time": raw_event_time,
                "provider": provider,
            }
        )
        if len(out) >= max_items:
            break
    return out


def _parse_tradingview_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = dtparser.parse(value)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


class TradingViewNewsCollector(Collector):
    name = "tradingview_news"

    def __init__(
        self,
        primary_url: str | None = None,
        fallback_url: str | None = None,
        max_items: int | None = None,
    ):
        self.primary_url = primary_url or settings.TRADINGVIEW_NEWS_FLOW_URL
        self.fallback_url = fallback_url or settings.TRADINGVIEW_NEWS_FALLBACK_URL
        self.max_items = max_items or settings.TRADINGVIEW_MAX_ITEMS
        self.client = ImpersonateHttpClient(
            impersonate=settings.CURL_IMPERSONATE_PROFILE,
            timeout=settings.CURL_IMPERSONATE_TIMEOUT_SEC,
        )

    async def collect(self):
        # Professor asked for /news-flow; we fetch it first, then fallback to /news if needed.
        html = await self.client.get_text(
            self.primary_url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://www.tradingview.com/",
            },
        )
        cards = _parse_tradingview_cards(html, base_url="https://www.tradingview.com", max_items=self.max_items)

        if not cards:
            fallback_html = await self.client.get_text(
                self.fallback_url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": "https://www.tradingview.com/",
                },
            )
            cards = _parse_tradingview_cards(
                fallback_html,
                base_url="https://www.tradingview.com",
                max_items=self.max_items,
            )

        items: list[NormalizedItem] = []
        for card in cards:
            published_at = _parse_tradingview_time(card.get("raw_event_time"))
            text_for_enrich = card["title"]
            key = "|".join([card["url"], card["title"], card.get("raw_event_time") or ""])
            external_id = hashlib.sha256(key.encode("utf-8")).hexdigest()

            items.append(
                NormalizedItem(
                    source="tradingview_news",
                    source_type=SourceType.SCRAPE,
                    external_id=external_id,
                    url=card["url"],
                    published_at=published_at,
                    detected_at=datetime.utcnow(),
                    title=card["title"],
                    summary=f"provider={card.get('provider')}" if card.get("provider") else None,
                    tickers=extract_tickers(text_for_enrich),
                    sentiment=vader_compound(text_for_enrich),
                    sentiment_model="vader",
                    raw={
                        "provider": card.get("provider"),
                        "raw_event_time": card.get("raw_event_time"),
                        "collector": "curl_impersonate",
                    },
                )
            )
        return items
