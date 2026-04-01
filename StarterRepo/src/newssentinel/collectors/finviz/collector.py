from __future__ import annotations

from datetime import datetime, timedelta
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from ..base import Collector
from ...config import settings
from ...enrich.canonical import build_story_key
from ...enrich.sentiment import vader_compound
from ...enrich.tickers import extract_tickers
from ...http.impersonate import ImpersonateHttpClient
from ...models.schema import NormalizedItem, SourceType

_MIN_RE = re.compile(r"(\d+)\s*min", re.IGNORECASE)
_HR_RE = re.compile(r"(\d+)\s*h(?:r|our)?s?", re.IGNORECASE)
_DAY_RE = re.compile(r"(\d+)\s*day", re.IGNORECASE)


def _parse_finviz_time(value: str | None, now: datetime | None = None) -> datetime | None:
    if not value:
        return None
    now = now or datetime.utcnow()
    s = value.strip().lower()

    m = _MIN_RE.match(s)
    if m:
        return now - timedelta(minutes=int(m.group(1)))

    m = _HR_RE.match(s)
    if m:
        return now - timedelta(hours=int(m.group(1)))

    m = _DAY_RE.match(s)
    if m:
        return now - timedelta(days=int(m.group(1)))

    try:
        dt = dtparser.parse(value, fuzzy=True)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


def _parse_finviz_rows(html: str, max_items: int = 100):
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for row in soup.select("tr.news_table-row"):
        main_link = row.select_one("a.nn-tab-link")
        if not main_link:
            continue

        href = (main_link.get("href") or "").strip()
        if not href:
            continue
        url = urljoin("https://finviz.com", href)
        title = main_link.get_text(" ", strip=True)
        if not title:
            continue

        age_node = row.select_one("td.news_date-cell")
        age_text = age_node.get_text(" ", strip=True) if age_node else None
        provider_node = row.select_one("span.news_date-cell")
        provider = provider_node.get_text(" ", strip=True) if provider_node else None

        tickers = [
            t.get_text(" ", strip=True)
            for t in row.select("a.stock-news-label")
            if t.get_text(" ", strip=True)
        ]

        out.append(
            {
                "url": url,
                "title": title,
                "age_text": age_text,
                "provider": provider,
                "tickers": tickers,
            }
        )
        if len(out) >= max_items:
            break
    return out


def _build_finviz_external_id(url: str, title: str) -> str:
    # Stable identity: do not include relative age text, which changes every poll.
    # This prevents old stories from resurfacing as "new" in continuous mode.
    return build_story_key(title=title, url=url)


class FinvizNewsCollector(Collector):
    name = "finviz_news"

    def __init__(self, url: str | None = None, max_items: int | None = None):
        self.url = url or settings.FINVIZ_NEWS_URL
        self.max_items = max_items or settings.FINVIZ_MAX_ITEMS
        self.client = ImpersonateHttpClient(
            impersonate=settings.CURL_IMPERSONATE_PROFILE,
            timeout=settings.CURL_IMPERSONATE_TIMEOUT_SEC,
        )

    async def collect(self):
        html = await self.client.get_text(
            self.url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://finviz.com/",
            },
        )

        rows = _parse_finviz_rows(html, max_items=self.max_items)
        now = datetime.utcnow()
        items: list[NormalizedItem] = []
        for row in rows:
            text_for_enrich = f"{row['title']} {row.get('provider') or ''}".strip()
            parsed_time = _parse_finviz_time(row.get("age_text"), now=now)
            external_id = _build_finviz_external_id(url=row["url"], title=row["title"])

            inferred_tickers = sorted(set(row.get("tickers", []) + extract_tickers(text_for_enrich)))
            items.append(
                NormalizedItem(
                    source="finviz_news",
                    source_type=SourceType.SCRAPE,
                    external_id=external_id,
                    url=row["url"],
                    published_at=parsed_time,
                    detected_at=datetime.utcnow(),
                    title=row["title"],
                    summary=row.get("provider"),
                    tickers=inferred_tickers,
                    sentiment=vader_compound(text_for_enrich),
                    sentiment_model="vader",
                    raw={
                        "provider": row.get("provider"),
                        "age_text": row.get("age_text"),
                        "collector": "curl_impersonate",
                    },
                )
            )
        return items
