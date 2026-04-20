import asyncio
import logging
import time

from ..config import settings
from ..logging import setup_logging
from ..queue.redis_streams import get_redis, read_batch, ack
from ..models.schema import NormalizedItem
from ..db.session import SessionLocal
from ..db.repo import upsert_news_items

log = logging.getLogger("ingest_worker")

async def run_forever():
    setup_logging()
    redis = await get_redis()
    log.info("Ingest worker started")

    while True:
        batch = await read_batch(
            redis,
            count=settings.INGEST_BATCH_SIZE,
            block_ms=settings.INGEST_BLOCK_MS,
        )
        if not batch:
            continue

        t0 = time.perf_counter()
        parsed: list[tuple[str, NormalizedItem]] = []
        ack_ids: list[str] = []
        parse_failures = 0
        for msg_id, payload in batch:
            try:
                item = NormalizedItem.model_validate_json(payload)
                parsed.append((msg_id, item))
            except Exception:
                parse_failures += 1
                ack_ids.append(msg_id)
                log.exception("Failed parse for msg_id=%s", msg_id)

        ingested = 0
        db_failures = 0
        async with SessionLocal() as session:
            try:
                if parsed:
                    ingested = await upsert_news_items(session, [item for _, item in parsed])
                    await session.commit()
                    ack_ids.extend(msg_id for msg_id, _ in parsed)
            except Exception:
                await session.rollback()
                log.exception("Bulk upsert failed; falling back to per-item upserts")
                for msg_id, item in parsed:
                    try:
                        async with session.begin_nested():
                            await upsert_news_items(session, [item])
                        ack_ids.append(msg_id)
                        ingested += 1
                    except Exception:
                        db_failures += 1
                        # Ack failed row for now to avoid redis pending growth; log for diagnostics.
                        ack_ids.append(msg_id)
                        log.exception("Failed ingest for msg_id=%s", msg_id)
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()
                    log.exception("Fallback commit failed")

        await ack(redis, ack_ids)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        log.info(
            "Ingest batch size=%d parsed=%d ingested=%d parse_fail=%d db_fail=%d acked=%d elapsed_ms=%.2f",
            len(batch),
            len(parsed),
            ingested,
            parse_failures,
            db_failures,
            len(ack_ids),
            elapsed_ms,
        )

async def main():
    await run_forever()

if __name__ == "__main__":
    asyncio.run(main())
