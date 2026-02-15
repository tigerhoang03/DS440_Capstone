import asyncio
from ..db.session import engine
from ..db.base import Base
from ..db import tables  # noqa: F401

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("DB initialized.")

if __name__ == "__main__":
    asyncio.run(main())
