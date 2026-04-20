import asyncio

from sqlalchemy import text

from ..db.session import engine


_DDL = [
    "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS canonical_url VARCHAR(2048)",
    "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS story_key VARCHAR(64)",
    "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS match_method VARCHAR(64)",
    "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS publication_lag_sec DOUBLE PRECISION",
    "CREATE INDEX IF NOT EXISTS ix_news_items_story_key ON news_items (story_key)",
    "CREATE INDEX IF NOT EXISTS ix_news_items_story_detected ON news_items (story_key, detected_at)",
    "CREATE INDEX IF NOT EXISTS ix_news_items_publication_lag_sec ON news_items (publication_lag_sec)",
]


async def main():
    async with engine.begin() as conn:
        for stmt in _DDL:
            await conn.execute(text(stmt))
    print("Story dedupe/lag schema upgrade complete.")


if __name__ == "__main__":
    asyncio.run(main())
