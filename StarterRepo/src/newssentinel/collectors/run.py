import argparse
import asyncio
from collections import deque
import logging
from typing import Optional

from ..config import settings
from ..logging import setup_logging
from ..models.schema import NormalizedItem
from ..queue.redis_streams import get_redis, publish_items
from .finviz.collector import FinvizNewsCollector
from .rss.demo import RssDemoCollector
from .rss.wires import WireSitesRssCollector
from .state_store import load_collector_seen_cache, save_collector_seen_cache
from .stocktwits.collector import StockTwitsCollector
from .tradingview.collector import TradingViewNewsCollector

log = logging.getLogger("collectors_runner")

COLLECTORS = {
    "rss_demo": lambda: RssDemoCollector(),
    "wire_sites_rss": lambda: WireSitesRssCollector(),
    "stocktwits_aapl": lambda: StockTwitsCollector(symbol="AAPL", pages=2),
    "finviz_news": lambda: FinvizNewsCollector(),
    "tradingview_news": lambda: TradingViewNewsCollector(
        max_items=settings.TRADINGVIEW_LIVE_MAX_ITEMS,
        live_only=True,
        max_published_age_sec=settings.TRADINGVIEW_LIVE_MAX_PUBLISHED_AGE_SEC,
        include_unknown_published=settings.TRADINGVIEW_LIVE_INCLUDE_UNKNOWN_PUBLISHED,
    ),
    "tradingview_news_backfill": lambda: TradingViewNewsCollector(
        max_items=settings.TRADINGVIEW_MAX_ITEMS,
        live_only=False,
    ),
}

COLLECTOR_GROUPS = {
    "all_live_news": [
        "wire_sites_rss",
        "finviz_news",
        "tradingview_news",
    ],
}

COLLECTOR_INTERVAL_SETTING_KEYS = {
    "wire_sites_rss": "WIRE_SITES_RSS_INTERVAL_SEC",
    "finviz_news": "FINVIZ_NEWS_INTERVAL_SEC",
    "tradingview_news": "TRADINGVIEW_NEWS_INTERVAL_SEC",
}

_collector_instances: dict[str, object] = {}
_collector_seen_ids: dict[str, set[str]] = {}
_collector_seen_order: dict[str, deque[str]] = {}


def _get_collector_instance(collector_name: str):
    collector = _collector_instances.get(collector_name)
    if collector is None:
        collector = COLLECTORS[collector_name]()
        _collector_instances[collector_name] = collector
        seen_ids: set[str]
        seen_order: deque[str]
        if settings.COLLECTOR_STATE_ENABLED:
            seen_ids, seen_order = load_collector_seen_cache(
                collector_name=collector_name,
                state_dir=settings.COLLECTOR_STATE_DIR,
                max_cache_size=settings.COLLECTOR_DELTA_CACHE_SIZE,
            )
            if seen_order:
                log.info(
                    "Loaded collector state collector=%s seen_cache_size=%d",
                    collector_name,
                    len(seen_order),
                )
        else:
            seen_ids, seen_order = set(), deque()

        _collector_seen_ids[collector_name] = seen_ids
        _collector_seen_order[collector_name] = seen_order
    return collector


def _filter_new_items(
    items: list[NormalizedItem],
    seen_ids: set[str],
    seen_order: deque[str],
    max_cache_size: int,
) -> tuple[list[NormalizedItem], int]:
    out: list[NormalizedItem] = []
    skipped = 0
    for item in items:
        key = item.external_id
        if key in seen_ids:
            skipped += 1
            continue
        out.append(item)
        seen_ids.add(key)
        seen_order.append(key)

        while len(seen_order) > max_cache_size:
            evicted = seen_order.popleft()
            seen_ids.discard(evicted)
    return out, skipped


async def collect_single(collector_name: str):
    collector = _get_collector_instance(collector_name)
    items = list(await collector.collect())
    seen_ids = _collector_seen_ids[collector_name]
    seen_order = _collector_seen_order[collector_name]
    filtered_items, skipped = _filter_new_items(
        items=items,
        seen_ids=seen_ids,
        seen_order=seen_order,
        max_cache_size=settings.COLLECTOR_DELTA_CACHE_SIZE,
    )
    if settings.COLLECTOR_STATE_ENABLED and filtered_items:
        save_collector_seen_cache(
            collector_name=collector_name,
            seen_order=seen_order,
            state_dir=settings.COLLECTOR_STATE_DIR,
            max_cache_size=settings.COLLECTOR_DELTA_CACHE_SIZE,
        )
    if skipped > 0:
        log.info("Collector %s delta-filtered %d previously seen item(s)", collector_name, skipped)
    return collector_name, filtered_items


def _interval_for_collector(collector_name: str, fallback_interval_sec: float) -> float:
    key = COLLECTOR_INTERVAL_SETTING_KEYS.get(collector_name)
    if key is None:
        return fallback_interval_sec

    configured = float(getattr(settings, key, fallback_interval_sec))
    if configured <= 0:
        return fallback_interval_sec
    return configured


async def _collect_single_safe(collector_name: str) -> tuple[str, list[NormalizedItem], Optional[Exception]]:
    try:
        _, items = await collect_single(collector_name)
        return collector_name, items, None
    except Exception as exc:  # pragma: no cover - defensive fallback
        return collector_name, [], exc


async def _publish_collector_items(redis, collector_name: str, items: list[NormalizedItem]) -> int:
    n = await publish_items(redis, items)
    print(f"Published {n} items from {collector_name}")
    return n


async def run_target_once(target: str, redis) -> int:
    if target in COLLECTORS:
        collector_name, items = await collect_single(target)
        total = await _publish_collector_items(redis, collector_name, items)
        print(f"Published {total} total items from target={target}")
        return total

    names = COLLECTOR_GROUPS[target]
    tasks = [asyncio.create_task(_collect_single_safe(name)) for name in names]

    total = 0
    for done in asyncio.as_completed(tasks):
        collector_name, items, error = await done
        if error is not None:
            log.error("Collector failed: %s (%s)", collector_name, error)
            continue
        total += await _publish_collector_items(redis, collector_name, items)

    print(f"Published {total} total items from target={target}")
    return total


async def run_once(target: str) -> int:
    redis = await get_redis()
    try:
        return await run_target_once(target, redis)
    finally:
        await redis.aclose()


async def run_collector_loop(collector_name: str, interval_sec: float, max_runs: int) -> None:
    if interval_sec < 1:
        log.warning("Very low interval (%ss) may trigger source rate limits", interval_sec)

    run_no = 0
    redis = await get_redis()
    try:
        while True:
            run_no += 1
            try:
                _, items = await collect_single(collector_name)
                published = await _publish_collector_items(redis, collector_name, items)
                log.info(
                    "Collector loop collector=%s run=%d published=%d",
                    collector_name,
                    run_no,
                    published,
                )
            except Exception:
                log.exception("Collector loop failed collector=%s run=%d", collector_name, run_no)

            if max_runs > 0 and run_no >= max_runs:
                log.info(
                    "Collector loop reached max runs (%d) for collector=%s; exiting",
                    max_runs,
                    collector_name,
                )
                break

            await asyncio.sleep(interval_sec)
    finally:
        await redis.aclose()


async def run_group_independent_loops(target: str, fallback_interval_sec: float, max_runs: int) -> None:
    tasks = []
    for collector_name in COLLECTOR_GROUPS[target]:
        interval_sec = _interval_for_collector(collector_name, fallback_interval_sec)
        log.info(
            "Starting grouped collector loop collector=%s interval_sec=%.2f",
            collector_name,
            interval_sec,
        )
        tasks.append(asyncio.create_task(run_collector_loop(collector_name, interval_sec, max_runs)))
    await asyncio.gather(*tasks)


async def main():
    setup_logging()
    targets = sorted([*COLLECTORS.keys(), *COLLECTOR_GROUPS.keys()])

    parser = argparse.ArgumentParser()
    parser.add_argument("--collector", required=True, choices=targets)
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=0.0,
        help=(
            "If > 0, run collector(s) continuously. For grouped targets, this is a fallback "
            "interval when no per-source interval env var is set."
        ),
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help=(
            "Optional cap for loop mode. 0 means run forever. For grouped targets in loop mode, "
            "this cap applies per source collector."
        ),
    )
    args = parser.parse_args()

    if args.interval_sec <= 0:
        await run_once(args.collector)
        return

    if args.collector in COLLECTOR_GROUPS:
        await run_group_independent_loops(
            target=args.collector,
            fallback_interval_sec=args.interval_sec,
            max_runs=args.max_runs,
        )
        return

    await run_collector_loop(
        collector_name=args.collector,
        interval_sec=args.interval_sec,
        max_runs=args.max_runs,
    )

if __name__ == "__main__":
    asyncio.run(main())
