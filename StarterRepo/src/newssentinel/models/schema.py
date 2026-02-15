from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional, List

from pydantic import BaseModel, Field

class SourceType(str, Enum):
    RSS = "rss"
    API = "api"
    SCRAPE = "scrape"
    BROKER = "broker"
    SOCIAL = "social"
    OCR = "ocr"

class NormalizedItem(BaseModel):
    # identity
    source: str = Field(..., description="e.g. finviz, stocktwits, wsj_rss, ibkr")
    source_type: SourceType
    external_id: str = Field(..., description="Unique id from the source (or stable hash)")
    url: Optional[str] = None

    # timing
    published_at: Optional[datetime] = None
    detected_at: datetime = Field(default_factory=lambda: datetime.utcnow())

    # content
    title: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None

    # enrichment
    tickers: List[str] = Field(default_factory=list)
    author: Optional[str] = None
    language: Optional[str] = None

    # sentiment
    sentiment: Optional[float] = Field(default=None, description="[-1,1] or [0,1] depending on model")
    sentiment_model: Optional[str] = None

    # raw passthrough (keep small)
    raw: dict[str, Any] = Field(default_factory=dict)
