import asyncio
import logging

from ..logging import setup_logging
from ..queue.redis_streams import get_redis, read_batch, ack
from ..models.schema import NormalizedItem
from ..db.session import SessionLocal
from ..db.repo import upsert_news_item

log = logging.getLogger("ingest_worker")

async def run_forever():
    setup_logging()
    redis = await get_redis()
    log.info("Ingest worker started")

    while True:
        batch = await read_batch(redis, count=200, block_ms=2000)
        if not batch:
            continue

        msg_ids = []
        async with SessionLocal() as session:
            for msg_id, payload in batch:
                msg_ids.append(msg_id)
                try:
                    item = NormalizedItem.model_validate_json(payload)
                    await upsert_news_item(session, item)
                except Exception:
                    log.exception("Failed ingest for msg_id=%s", msg_id)

        await ack(redis, msg_ids)

async def main():
    await run_forever()

if __name__ == "__main__":
    asyncio.run(main())
