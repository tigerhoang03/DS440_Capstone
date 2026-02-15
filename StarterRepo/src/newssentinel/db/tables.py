from sqlalchemy import String, DateTime, Float, JSON, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .base import Base

class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, index=True)

    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(8192), nullable=True)
    content: Mapped[str | None] = mapped_column(String, nullable=True)

    tickers: Mapped[list[str]] = mapped_column(JSON, default=list)
    author: Mapped[str | None] = mapped_column(String(256), nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)

    sentiment: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    sentiment_model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    raw: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_source_external_id"),
        Index("ix_news_items_source_detected", "source", "detected_at"),
        Index("ix_news_items_published", "published_at"),
    )
