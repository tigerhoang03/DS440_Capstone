from datetime import datetime, timedelta

from newssentinel.db.repo import build_news_row_data
from newssentinel.models.schema import NormalizedItem, SourceType


def test_build_news_row_data_clamps_future_published_lag_to_zero():
    detected_at = datetime(2026, 4, 19, 20, 0, 0)
    item = NormalizedItem(
        source="finviz_news",
        source_type=SourceType.SCRAPE,
        external_id="future-story",
        url="https://example.com/future-story",
        published_at=detected_at + timedelta(seconds=30),
        detected_at=detected_at,
        title="Future-dated source timestamp",
    )

    row = build_news_row_data(item)

    assert row["publication_lag_sec"] == 0.0
