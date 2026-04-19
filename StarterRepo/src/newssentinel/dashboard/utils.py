from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import pandas as pd


def get_or_set_session_started_at(session_state: dict[str, Any], now: datetime | None = None) -> datetime:
    value = session_state.get("session_started_at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)

    started_at = now or datetime.utcnow()
    session_state["session_started_at"] = started_at.isoformat()
    return started_at


def looks_like_ticker_query(query: str | None) -> bool:
    if not query:
        return False
    normalized = query.strip().upper()
    if not normalized:
        return False
    candidate = normalized.replace(".", "").replace("-", "")
    return 1 <= len(normalized) <= 8 and candidate.isalnum()


def format_timestamp(value: Any) -> str:
    if value is None or value == "":
        return "-"
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return "-"
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def format_tickers(value: Any) -> str:
    if isinstance(value, list):
        cleaned = [str(item).upper() for item in value if str(item).strip()]
        return ", ".join(cleaned) if cleaned else "-"
    if value:
        return str(value)
    return "-"


def compact_url(url: str | None) -> str:
    if not url:
        return "-"
    parsed = urlparse(url)
    host = parsed.netloc.replace("www.", "")
    if not host:
        return url
    return host


def build_feed_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    table = pd.DataFrame(
        {
            "Detected": df.get("detected_recency", pd.Series(["-"] * len(df))),
            "Published": df.get("published_recency", pd.Series(["-"] * len(df))),
            "Lag (s)": pd.to_numeric(df.get("publication_lag_sec"), errors="coerce").round(0),
            "Source": df.get("source", pd.Series(["-"] * len(df))),
            "Tickers": df.get("tickers", pd.Series([[]] * len(df))).apply(format_tickers),
            "Sentiment": df.get("sentiment_label", pd.Series(["-"] * len(df))).fillna("-"),
            "Score": pd.to_numeric(df.get("sentiment"), errors="coerce").round(3),
            "Headline": df.get("title", pd.Series(["-"] * len(df))).fillna("-"),
            "Link": df.get("url", pd.Series(["-"] * len(df))).apply(compact_url),
        }
    )
    return table.fillna("-")


def sort_news_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "detected_at" not in df.columns:
        return df
    return df.sort_values("detected_at", ascending=False)
