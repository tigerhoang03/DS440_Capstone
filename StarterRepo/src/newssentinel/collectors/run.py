import argparse
import asyncio

from ..logging import setup_logging
from ..queue.redis_streams import get_redis, publish_items
from .finviz.collector import FinvizNewsCollector
from .rss.demo import RssDemoCollector
from .rss.wires import WireSitesRssCollector
from .stocktwits.collector import StockTwitsCollector
from .tradingview.collector import TradingViewNewsCollector

COLLECTORS = {
    "rss_demo": lambda: RssDemoCollector(),
    "wire_sites_rss": lambda: WireSitesRssCollector(),
    "stocktwits_aapl": lambda: StockTwitsCollector(symbol="AAPL", pages=2),
    "finviz_news": lambda: FinvizNewsCollector(),
    "tradingview_news": lambda: TradingViewNewsCollector(),
}

async def main():
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--collector", required=True, choices=sorted(COLLECTORS.keys()))
    args = parser.parse_args()

    collector = COLLECTORS[args.collector]()
    items = list(await collector.collect())

    redis = await get_redis()
    n = await publish_items(redis, items)
    await redis.aclose()
    print(f"Published {n} items from {args.collector}")

if __name__ == "__main__":
    asyncio.run(main())
