from __future__ import annotations

import argparse
import asyncio
import logging
import time
from typing import Protocol

from ..config import settings
from ..db.repo import list_news_needing_sentiment, update_news_sentiment
from ..db.session import SessionLocal
from ..enrich.sentiment import FinbertSentiment, FinbertTitleScorer
from ..logging import setup_logging

log = logging.getLogger("sentiment_worker")


class TitleScorer(Protocol):
    def score_batch(self, titles: list[str]) -> list[FinbertSentiment | None]:
        ...


async def run_once(
    scorer: TitleScorer,
    *,
    limit: int,
    batch_size: int,
    model_tag: str,
) -> int:
    async with SessionLocal() as session:
        rows = await list_news_needing_sentiment(session, limit=limit, model_name=model_tag)
        if not rows:
            return 0

        enriched = 0
        started = time.perf_counter()
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            titles = [row.title or "" for row in batch]
            results = scorer.score_batch(titles)

            for row, result in zip(batch, results, strict=True):
                if result is None:
                    continue
                await update_news_sentiment(session, row.id, result, model_tag=model_tag)
                enriched += 1

        await session.commit()
        elapsed_ms = (time.perf_counter() - started) * 1000
        log.info(
            "FinBERT sentiment cycle candidates=%d enriched=%d elapsed_ms=%.2f",
            len(rows),
            enriched,
            elapsed_ms,
        )
        return enriched


async def run_forever(once: bool = False) -> None:
    setup_logging()
    scorer = FinbertTitleScorer(settings.FINBERT_MODEL_NAME)
    log.info(
        "Sentiment worker started model=%s batch_size=%d max_rows=%d",
        settings.FINBERT_MODEL_NAME,
        settings.FINBERT_BATCH_SIZE,
        settings.FINBERT_MAX_ROWS_PER_CYCLE,
    )

    while True:
        try:
            await run_once(
                scorer,
                limit=settings.FINBERT_MAX_ROWS_PER_CYCLE,
                batch_size=settings.FINBERT_BATCH_SIZE,
                model_tag=settings.SENTIMENT_MODEL,
            )
        except Exception:
            log.exception("FinBERT sentiment cycle failed")

        if once:
            return
        await asyncio.sleep(settings.FINBERT_POLL_INTERVAL_SEC)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich news rows with FinBERT title sentiment.")
    parser.add_argument("--once", action="store_true", help="Run one enrichment cycle and exit.")
    args = parser.parse_args()
    await run_forever(once=args.once)


if __name__ == "__main__":
    asyncio.run(main())
