from __future__ import annotations
from datetime import datetime
import hashlib
import feedparser
import httpx
from dateutil import parser as dtparser

from ..base import Collector
from ...config import settings
from ...models.schema import NormalizedItem, SourceType
from ...enrich.tickers import extract_tickers
from ...enrich.sentiment import vader_compound

class RssDemoCollector(Collector):
    name = "rss_demo"

    async def collect(self):
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(settings.RSS_DEMO_URL)
            r.raise_for_status()

        feed = feedparser.parse(r.text)
        items = []
        for e in feed.entries[:50]:
            url = getattr(e, "link", None)
            title = getattr(e, "title", None)
            summary = getattr(e, "summary", None)

            published_at = None
            if getattr(e, "published", None):
                try:
                    published_at = dtparser.parse(e.published)
                except Exception:
                    published_at = None

            # stable external id: link + title hash
            key = (url or "") + "|" + (title or "")
            external_id = hashlib.sha256(key.encode("utf-8")).hexdigest()

            text_for_enrich = " ".join([t for t in [title, summary] if t])
            tickers = extract_tickers(text_for_enrich)
            sent = vader_compound(text_for_enrich)

            items.append(
                NormalizedItem(
                    source="wsj_rss_demo",
                    source_type=SourceType.RSS,
                    external_id=external_id,
                    url=url,
                    published_at=published_at,
                    detected_at=datetime.utcnow(),
                    title=title,
                    summary=summary,
                    tickers=tickers,
                    sentiment=sent,
                    sentiment_model="vader",
                    raw={"feed_title": getattr(feed.feed, "title", None)},
                )
            )
        return items
