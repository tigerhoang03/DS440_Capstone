from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from ..config import settings

engine = create_async_engine(settings.postgres_dsn, pool_pre_ping=True)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
