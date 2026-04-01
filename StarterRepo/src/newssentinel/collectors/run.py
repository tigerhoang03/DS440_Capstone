import argparse
import asyncio
from collections import deque
import logging

from ..config import settings
from ..logging import setup_logging
from ..models.schema import NormalizedItem
from ..queue.redis_streams import get_redis, publish_items
from .finviz.collector import FinvizNewsCollector
from .rss.demo import RssDemoCollector
from .rss.wires import WireSitesRssCollector
from .stocktwits.collector import StockTwitsCollector
from .tradingview.collector import TradingViewNewsCollector

log = logging.getLogger("collectors_runner")

COLLECTORS = {
    "rss_demo": lambda: RssDemoCollector(),
    "wire_sites_rss": lambda: WireSitesRssCollector(),
    "stocktwits_aapl": lambda: StockTwitsCollector(symbol="AAPL", pages=2),
    "finviz_news": lambda: FinvizNewsCollector(),
    "tradingview_news": lambda: TradingViewNewsCollector(),
}

COLLECTOR_GROUPS = {
    "all_live_news": [
        "wire_sites_rss",
        "finviz_news",
        "tradingview_news",
    ],
}

_collector_instances: dict[str, object] = {}
_collector_seen_ids: dict[str, set[str]] = {}
_collector_seen_order: dict[str, deque[str]] = {}


def _get_collector_instance(collector_name: str):
    collector = _collector_instances.get(collector_name)
    if collector is None:
        collector = COLLECTORS[collector_name]()
        _collector_instances[collector_name] = collector
        _collector_seen_ids[collector_name] = set()
        _collector_seen_order[collector_name] = deque()
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
    if skipped > 0:
        log.info("Collector %s delta-filtered %d previously seen item(s)", collector_name, skipped)
    return collector_name, filtered_items


async def run_target(target: str):
    if target in COLLECTORS:
        return [await collect_single(target)]

    names = COLLECTOR_GROUPS[target]
    results = await asyncio.gather(
        *(collect_single(name) for name in names),
        return_exceptions=True,
    )

    out = []
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            log.exception("Collector failed: %s", name, exc_info=result)
            continue
        out.append(result)
    return out


async def publish_collected(target: str, collected) -> int:
    redis = await get_redis()
    try:
        total = 0
        for collector_name, items in collected:
            n = await publish_items(redis, items)
            total += n
            print(f"Published {n} items from {collector_name}")
        print(f"Published {total} total items from target={target}")
        return total
    finally:
        await redis.aclose()


async def run_once(target: str) -> int:
    collected = await run_target(target)
    return await publish_collected(target, collected)


async def main():
    setup_logging()
    targets = sorted([*COLLECTORS.keys(), *COLLECTOR_GROUPS.keys()])

    parser = argparse.ArgumentParser()
    parser.add_argument("--collector", required=True, choices=targets)
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=0.0,
        help="If > 0, run collector(s) continuously every N seconds.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Optional cap for loop mode. 0 means run forever.",
    )
    args = parser.parse_args()

    if args.interval_sec <= 0:
        await run_once(args.collector)
        return

    if args.interval_sec < 1:
        log.warning("Very low interval (%ss) may trigger source rate limits", args.interval_sec)

    run_no = 0
    while True:
        run_no += 1
        try:
            total = await run_once(args.collector)
            log.info("Collector loop run=%d published_total=%d", run_no, total)
        except Exception:
            log.exception("Collector loop run=%d failed", run_no)

        if args.max_runs > 0 and run_no >= args.max_runs:
            log.info("Collector loop reached max runs (%d); exiting", args.max_runs)
            break

        await asyncio.sleep(args.interval_sec)

if __name__ == "__main__":
    asyncio.run(main())
