import argparse
import asyncio
import logging

from ..logging import setup_logging
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


async def collect_single(collector_name: str):
    collector = COLLECTORS[collector_name]()
    items = list(await collector.collect())
    return collector_name, items


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


async def main():
    setup_logging()
    targets = sorted([*COLLECTORS.keys(), *COLLECTOR_GROUPS.keys()])

    parser = argparse.ArgumentParser()
    parser.add_argument("--collector", required=True, choices=targets)
    args = parser.parse_args()

    collected = await run_target(args.collector)
    redis = await get_redis()
    try:
        total = 0
        for collector_name, items in collected:
            n = await publish_items(redis, items)
            total += n
            print(f"Published {n} items from {collector_name}")
        print(f"Published {total} total items from target={args.collector}")
    finally:
        await redis.aclose()

if __name__ == "__main__":
    asyncio.run(main())
