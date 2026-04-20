import argparse
import asyncio
from ..db.session import engine
from ..db.base import Base
from ..db import tables  # noqa: F401


async def init_db(reset: bool = False):
    async with engine.begin() as conn:
        if reset:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    if reset:
        print("DB reset and initialized.")
    else:
        print("DB initialized.")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables.")
    args = parser.parse_args()
    await init_db(reset=args.reset)

if __name__ == "__main__":
    asyncio.run(main())
