from __future__ import annotations
from datetime import datetime
import asyncio
import hashlib
import random
import httpx

from ..base import Collector
from ...models.schema import NormalizedItem, SourceType
from ...enrich.sentiment import vader_compound

class StockTwitsCollector(Collector):
    name = "stocktwits"

    def __init__(self, symbol: str = "AAPL", pages: int = 2, delay_range=(0.3, 0.9)):
        self.symbol = symbol.upper()
        self.pages = pages
        self.delay_range = delay_range

    async def collect(self):
        items = []
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as client:
            max_id = None
            for _ in range(self.pages):
                url = f"https://api.stocktwits.com/api/2/streams/symbol/{self.symbol}.json"
                params = {}
                if max_id:
                    params["max"] = max_id
                r = await client.get(url, params=params)
                r.raise_for_status()
                data = r.json()

                for msg in data.get("messages", []):
                    msg_id = str(msg.get("id"))
                    body = msg.get("body", "")
                    created_at = msg.get("created_at")
                    published_at = None
                    if created_at:
                        try:
                            # StockTwits timestamps are ISO-like; parse manually to avoid deps
                            published_at = datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
                        except Exception:
                            published_at = None

                    external_id = msg_id or hashlib.sha256(body.encode("utf-8")).hexdigest()
                    url_guess = f"https://stocktwits.com/message/{msg_id}" if msg_id else None

                    sent = vader_compound(body)
                    items.append(
                        NormalizedItem(
                            source=f"stocktwits_{self.symbol}",
                            source_type=SourceType.SOCIAL,
                            external_id=external_id,
                            url=url_guess,
                            published_at=published_at,
                            detected_at=datetime.utcnow(),
                            title=None,
                            summary=body[:300],
                            content=body,
                            tickers=[self.symbol],
                            author=(msg.get("user") or {}).get("username"),
                            sentiment=sent,
                            sentiment_model="vader",
                            raw={"likes": msg.get("likes", {}).get("total")},
                        )
                    )

                # pagination: StockTwits uses "cursor" for some endpoints; this one uses "max"
                max_id = data.get("cursor", {}).get("max") or None

                await asyncio.sleep(random.uniform(*self.delay_range))
        return items
