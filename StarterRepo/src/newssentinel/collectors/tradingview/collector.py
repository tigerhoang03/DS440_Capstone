from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import logging
import re
from typing import Any
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
_GATED_TITLE_PATTERNS = (
    "sign in",
    "please sign in",
    "exclusive news",
    "sign in to read",
    "sign in to see",
    "login",
    "log in",
)
log = logging.getLogger("tradingview_news_collector")


def _tradingview_headers(referer: str = "https://www.tradingview.com/") -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": referer,
        "Sec-CH-UA": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
    }


def _tradingview_api_headers(referer: str = "https://www.tradingview.com/news-flow/") -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Origin": "https://www.tradingview.com",
        "Pragma": "no-cache",
        "Referer": referer,
        "Sec-CH-UA": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
    }


def _is_gated_tradingview_title(title: str | None) -> bool:
    normalized = (title or "").strip().lower()
    return bool(normalized and any(pattern in normalized for pattern in _GATED_TITLE_PATTERNS))


def _filter_gated_cards(cards: list[dict]) -> tuple[list[dict], int]:
    usable = [card for card in cards if not _is_gated_tradingview_title(card.get("title"))]
    return usable, len(cards) - len(usable)


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
                "collector": "curl_impersonate_html",
            }
        )

    out.sort(key=lambda card: _parse_tradingview_time(card.get("raw_event_time")) or datetime.min, reverse=True)
    return out[:max_items]


def _parse_tradingview_api_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)
    value_str = str(value).strip()
    if not value_str:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", value_str):
        timestamp = float(value_str)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)
    return _parse_tradingview_time(value_str)


def _parse_tradingview_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = dtparser.parse(value)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


def _extract_related_symbol_tickers(related_symbols: Any) -> list[str]:
    tickers: set[str] = set()
    if not isinstance(related_symbols, list):
        return []

    for item in related_symbols:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        ticker = symbol.rsplit(":", 1)[-1].strip()
        if re.fullmatch(r"[A-Z][A-Z0-9./_-]{0,14}", ticker):
            tickers.add(ticker)
    return sorted(tickers)


def _parse_tradingview_api_items(data: dict[str, Any], max_items: int = 100) -> list[dict]:
    raw_items = data.get("items", [])
    if not isinstance(raw_items, list):
        return []

    cards: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or "").strip()
        if not title:
            continue

        provider = item.get("provider") if isinstance(item.get("provider"), dict) else {}
        provider_name = provider.get("name") or provider.get("id")
        story_path = str(item.get("storyPath") or "").strip()
        link = str(item.get("link") or "").strip()
        url = link or (urljoin("https://www.tradingview.com", story_path) if story_path else None)
        published_at = _parse_tradingview_api_time(item.get("published"))

        cards.append(
            {
                "api_id": str(item.get("id") or "").strip() or None,
                "url": url,
                "title": title,
                "raw_event_time": published_at.isoformat() if published_at else None,
                "provider": provider_name,
                "provider_id": provider.get("id"),
                "tickers": _extract_related_symbol_tickers(item.get("relatedSymbols")),
                "collector": "tradingview_mediator_api",
            }
        )

    cards.sort(
        key=lambda card: _parse_tradingview_time(card.get("raw_event_time")) or datetime.min,
        reverse=True,
    )
    return cards[:max_items]


class TradingViewNewsCollector(Collector):
    name = "tradingview_news"

    def __init__(
        self,
        primary_url: str | None = None,
        fallback_url: str | None = None,
        api_url: str | None = None,
        max_items: int | None = None,
        live_only: bool = True,
        max_published_age_sec: int | None = None,
        include_unknown_published: bool | None = None,
    ):
        self.primary_url = primary_url or settings.TRADINGVIEW_NEWS_FLOW_URL
        self.fallback_url = fallback_url or settings.TRADINGVIEW_NEWS_FALLBACK_URL
        self.api_url = api_url or settings.TRADINGVIEW_NEWS_API_URL
        self.max_items = max_items or settings.TRADINGVIEW_MAX_ITEMS
        self.live_only = live_only
        self.max_published_age_sec = (
            max_published_age_sec
            if max_published_age_sec is not None
            else settings.TRADINGVIEW_LIVE_MAX_PUBLISHED_AGE_SEC
        )
        self.include_unknown_published = (
            include_unknown_published
            if include_unknown_published is not None
            else settings.TRADINGVIEW_LIVE_INCLUDE_UNKNOWN_PUBLISHED
        )
        self._last_cards_hash: str | None = None
        self._gated_only_cycles = 0
        self.client = self._new_client()

    def _new_client(self) -> ImpersonateHttpClient:
        return ImpersonateHttpClient(
            impersonate=settings.CURL_IMPERSONATE_PROFILE,
            timeout=settings.CURL_IMPERSONATE_TIMEOUT_SEC,
        )

    def _reset_client(self) -> None:
        self.client = self._new_client()
        self._last_cards_hash = None
        log.warning("TradingView reset curl-impersonate session after repeated gated responses")

    def _record_gating_result(self, *, raw_count: int, gated_count: int, usable_count: int) -> None:
        gated_ratio = (gated_count / raw_count) if raw_count else 0.0
        gated_dominates = raw_count > 0 and gated_ratio >= settings.TRADINGVIEW_GATED_DOMINANCE_RATIO
        if usable_count == 0 and gated_count > 0:
            self._gated_only_cycles += 1
        elif gated_dominates:
            self._gated_only_cycles += 1
        else:
            self._gated_only_cycles = 0

        if self._gated_only_cycles >= settings.TRADINGVIEW_GATED_SESSION_RESET_THRESHOLD:
            self._gated_only_cycles = 0
            self._reset_client()

    async def _fetch_cards(self, url: str, referer: str) -> tuple[list[dict], int, int]:
        html = await self.client.get_text(url, headers=_tradingview_headers(referer=referer))
        raw_cards = _parse_tradingview_cards(
            html,
            base_url="https://www.tradingview.com",
            max_items=self.max_items,
        )
        usable_cards, gated_count = _filter_gated_cards(raw_cards)
        if gated_count:
            log.info(
                "TradingView skipped gated cards url=%s raw=%d gated=%d usable=%d",
                url,
                len(raw_cards),
                gated_count,
                len(usable_cards),
            )
        return usable_cards, len(raw_cards), gated_count

    async def _fetch_api_cards(self) -> tuple[list[dict], int, int]:
        data = await self.client.get_json(
            self.api_url,
            params={
                "filter": "lang:en",
                "client": "screener",
                "streaming": "true",
            },
            headers=_tradingview_api_headers(),
        )
        raw_cards = _parse_tradingview_api_items(data, max_items=self.max_items)
        usable_cards, gated_count = _filter_gated_cards(raw_cards)
        if gated_count:
            log.info(
                "TradingView API skipped gated cards raw=%d gated=%d usable=%d",
                len(raw_cards),
                gated_count,
                len(usable_cards),
            )
        return usable_cards, len(raw_cards), gated_count

    async def collect(self):
        try:
            cards, api_raw_count, api_gated_count = await self._fetch_api_cards()
            raw_count = api_raw_count
            gated_count = api_gated_count
            api_unusable = not cards
        except Exception as exc:
            log.warning("TradingView API fetch failed; falling back to HTML scraping: %s", exc)
            cards = []
            raw_count = 0
            gated_count = 0
            api_unusable = True

        if api_unusable:
            # Professor asked for /news-flow; HTML scraping remains a fallback if the JSON API changes.
            cards, primary_raw_count, primary_gated_count = await self._fetch_cards(
                self.primary_url,
                referer="https://www.tradingview.com/",
            )
            raw_count += primary_raw_count
            gated_count += primary_gated_count

            primary_gated_ratio = (primary_gated_count / primary_raw_count) if primary_raw_count else 0.0
            primary_unusable = not cards or primary_gated_ratio >= settings.TRADINGVIEW_GATED_DOMINANCE_RATIO
        else:
            primary_raw_count = 0
            primary_gated_count = 0
            primary_unusable = False

        if primary_unusable:
            fallback_cards, fallback_raw_count, fallback_gated_count = await self._fetch_cards(
                self.fallback_url,
                referer=self.primary_url,
            )
            log.info(
                "TradingView fallback used primary_raw=%d primary_gated=%d fallback_raw=%d fallback_gated=%d fallback_usable=%d",
                primary_raw_count,
                primary_gated_count,
                fallback_raw_count,
                fallback_gated_count,
                len(fallback_cards),
            )
            cards = fallback_cards
            raw_count += fallback_raw_count
            gated_count += fallback_gated_count

        self._record_gating_result(
            raw_count=raw_count,
            gated_count=gated_count,
            usable_count=len(cards),
        )

        now = datetime.utcnow()
        eligible_cards: list[tuple[dict, datetime | None]] = []
        stale_skipped = 0
        unknown_time_skipped = 0
        for card in cards:
            published_at = _parse_tradingview_time(card.get("raw_event_time"))
            if self.live_only:
                if published_at is None and not self.include_unknown_published:
                    unknown_time_skipped += 1
                    continue
                if published_at is not None and self.max_published_age_sec > 0:
                    age_sec = max((now - published_at).total_seconds(), 0.0)
                    if age_sec > self.max_published_age_sec:
                        stale_skipped += 1
                        continue
            eligible_cards.append((card, published_at))

        if self.live_only and (stale_skipped > 0 or unknown_time_skipped > 0):
            log.info(
                "TradingView live freshness gate kept=%d stale_skipped=%d unknown_time_skipped=%d",
                len(eligible_cards),
                stale_skipped,
                unknown_time_skipped,
            )

        snapshot = "|".join(
            f"{card.get('url') or ''}|{card['title']}|{card.get('raw_event_time') or ''}"
            for card, _published_at in eligible_cards
        )
        cards_hash = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        if cards_hash == self._last_cards_hash:
            return []
        self._last_cards_hash = cards_hash

        items: list[NormalizedItem] = []
        for card, published_at in eligible_cards:
            text_for_enrich = card["title"]
            key = "|".join([card.get("url") or "", card["title"], card.get("raw_event_time") or ""])
            external_id = card.get("api_id") or hashlib.sha256(key.encode("utf-8")).hexdigest()
            tickers = sorted(set(extract_tickers(text_for_enrich) + (card.get("tickers") or [])))
            collector_name = card.get("collector") or "curl_impersonate_html"

            items.append(
                NormalizedItem(
                    source="tradingview_news",
                    source_type=SourceType.API
                    if collector_name == "tradingview_mediator_api"
                    else SourceType.SCRAPE,
                    external_id=external_id,
                    url=card.get("url"),
                    published_at=published_at,
                    detected_at=datetime.utcnow(),
                    title=card["title"],
                    summary=f"provider={card.get('provider')}" if card.get("provider") else None,
                    tickers=tickers,
                    sentiment=vader_compound(text_for_enrich),
                    sentiment_model="vader",
                    raw={
                        "provider": card.get("provider"),
                        "provider_id": card.get("provider_id"),
                        "raw_event_time": card.get("raw_event_time"),
                        "collector": collector_name,
                    },
                )
            )
        return items
