from __future__ import annotations

from datetime import datetime
import hashlib
import logging
import re
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dtparser
import feedparser
import httpx

from ..base import Collector
from ...config import settings
from ...enrich.sentiment import vader_compound
from ...enrich.tickers import extract_tickers
from ...models.schema import NormalizedItem, SourceType

log = logging.getLogger("wire_sites_rss_collector")


def _to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = dtparser.parse(value)
        # Keep DB values naive (same pattern as existing collectors/tables)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


def _normalize_source_name(source_url: str) -> str:
    if "prnewswire.com" in source_url:
        return "prnewswire_rss"
    if "globenewswire.com" in source_url:
        return "globenewswire_rss"
    return "wire_rss"


def _build_conditional_headers(feed_http_cache: dict[str, str] | None) -> dict[str, str]:
    if not feed_http_cache:
        return {}
    headers: dict[str, str] = {}
    etag = feed_http_cache.get("etag")
    if etag:
        headers["If-None-Match"] = etag
    last_modified = feed_http_cache.get("last_modified")
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def _update_feed_http_cache(
    cache: dict[str, dict[str, str]],
    feed_url: str,
    response_headers: dict[str, str],
) -> None:
    etag = response_headers.get("ETag")
    last_modified = response_headers.get("Last-Modified")
    if not etag and not last_modified:
        return
    cache[feed_url] = {
        "etag": etag or "",
        "last_modified": last_modified or "",
    }


def _discover_rss_links(listing_url: str, html: str, max_links: int) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen: set[str] = set()

    def maybe_add(raw_href: str) -> None:
        candidate = urljoin(listing_url, raw_href.strip())
        lower = candidate.lower()
        has_feed_suffix = lower.endswith(".xml") or lower.endswith(".rss") or lower.endswith(".atom")
        looks_like_feed_query = "format=rss" in lower or "output=rss" in lower
        if not (has_feed_suffix or looks_like_feed_query):
            return
        if candidate in seen:
            return
        seen.add(candidate)
        links.append(candidate)

    for tag in soup.find_all("a", href=True):
        maybe_add(tag["href"])
        if len(links) >= max_links:
            break

    if len(links) >= max_links:
        return links

    # Some pages (notably PR Newswire) keep RSS URLs inside javascript strings,
    # e.g. window.location.href='\/rss\/news\u002Dreleases\u002Dlist.rss'
    for raw in re.findall(r"window\.location\.href='([^']+)'", html):
        decoded = raw.replace("\\/", "/")
        try:
            decoded = decoded.encode("utf-8").decode("unicode_escape")
        except Exception:
            pass
        maybe_add(decoded)
        if len(links) >= max_links:
            break
    return links


class WireSitesRssCollector(Collector):
    """
    Reads PR Newswire + GlobeNewswire RSS data.

    Behavior:
    - If source URL already returns RSS/Atom XML, parse directly.
    - If source URL is a listing page, discover feed links from HTML and parse each feed.
    """

    name = "wire_sites_rss"

    def __init__(
        self,
        source_urls: Iterable[str] | None = None,
        max_feeds_per_source: int | None = None,
        max_items_per_feed: int | None = None,
    ):
        self.source_urls = list(
            source_urls
            or [
                settings.PRNEWSWIRE_RSS_SOURCE_URL,
                settings.GLOBENEWSWIRE_RSS_SOURCE_URL,
            ]
        )
        self.max_feeds_per_source = max_feeds_per_source or settings.WIRE_RSS_MAX_FEEDS_PER_SOURCE
        self.max_items_per_feed = max_items_per_feed or settings.WIRE_RSS_MAX_ITEMS_PER_FEED
        self._feed_http_cache: dict[str, dict[str, str]] = {}

    async def _resolve_feed_urls(self, client: httpx.AsyncClient, source_url: str) -> list[str]:
        r = await client.get(source_url, follow_redirects=True)
        r.raise_for_status()

        body = r.text
        body_l = body.lstrip().lower()
        is_xml = body_l.startswith("<?xml") or "<rss" in body_l[:600] or "<feed" in body_l[:600]
        if is_xml:
            return [source_url]

        discovered = _discover_rss_links(
            listing_url=source_url,
            html=body,
            max_links=self.max_feeds_per_source,
        )
        return discovered

    def _build_item(self, entry, source_url: str, feed_title: str | None) -> NormalizedItem:
        link = entry.get("link")
        title = entry.get("title")
        summary = entry.get("summary") or entry.get("description")
        content = None
        if entry.get("content") and isinstance(entry.get("content"), list):
            first = entry["content"][0]
            if isinstance(first, dict):
                content = first.get("value")

        published = entry.get("published") or entry.get("updated")
        published_at = _to_datetime(published)

        key = "|".join(
            [
                source_url,
                str(link or ""),
                str(title or ""),
                str(published or ""),
            ]
        )
        external_id = hashlib.sha256(key.encode("utf-8")).hexdigest()

        text_for_enrich = " ".join([t for t in [title, summary, content] if t])

        return NormalizedItem(
            source=_normalize_source_name(source_url),
            source_type=SourceType.RSS,
            external_id=external_id,
            url=link,
            published_at=published_at,
            detected_at=datetime.utcnow(),
            title=title,
            summary=summary,
            content=content,
            tickers=extract_tickers(text_for_enrich),
            sentiment=vader_compound(text_for_enrich),
            sentiment_model="vader",
            raw={
                "feed_title": feed_title,
                "feed_source_url": source_url,
                "author": entry.get("author"),
            },
        )

    async def collect(self):
        items: list[NormalizedItem] = []
        async with httpx.AsyncClient(timeout=settings.WIRE_RSS_TIMEOUT_SEC) as client:
            for source_url in self.source_urls:
                try:
                    feed_urls = await self._resolve_feed_urls(client, source_url)
                except Exception:
                    log.exception("Failed resolving feed urls for source=%s", source_url)
                    continue

                for feed_url in feed_urls:
                    try:
                        request_headers = _build_conditional_headers(self._feed_http_cache.get(feed_url))
                        r = await client.get(feed_url, follow_redirects=True, headers=request_headers)
                        if r.status_code == 304:
                            continue
                        r.raise_for_status()
                        _update_feed_http_cache(
                            cache=self._feed_http_cache,
                            feed_url=feed_url,
                            response_headers=dict(r.headers),
                        )

                        parsed = feedparser.parse(r.text)
                        feed_title = parsed.feed.get("title")
                        for entry in parsed.entries[: self.max_items_per_feed]:
                            items.append(self._build_item(entry, source_url=feed_url, feed_title=feed_title))
                    except httpx.HTTPStatusError as exc:
                        status = exc.response.status_code if exc.response is not None else None
                        if status == 404:
                            log.warning("Skipping unavailable feed (404): %s", feed_url)
                            continue
                        log.exception("HTTP error fetching/parsing feed_url=%s", feed_url)
                        continue
                    except Exception:
                        log.exception("Failed fetching/parsing feed_url=%s", feed_url)
                        continue
        return items
