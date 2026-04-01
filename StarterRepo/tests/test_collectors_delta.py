from collections import deque
from datetime import datetime

from newssentinel.collectors.run import _filter_new_items
from newssentinel.models.schema import NormalizedItem, SourceType


def _item(external_id: str) -> NormalizedItem:
    return NormalizedItem(
        source="delta_test",
        source_type=SourceType.API,
        external_id=external_id,
        url=f"https://example.com/{external_id}",
        detected_at=datetime.now(),
        title=f"title-{external_id}",
    )


def test_filter_new_items_skips_previously_seen_ids():
    seen_ids = set()
    seen_order = deque()
    items = [_item("a"), _item("b"), _item("a"), _item("c"), _item("b")]
    out, skipped = _filter_new_items(
        items=items,
        seen_ids=seen_ids,
        seen_order=seen_order,
        max_cache_size=100,
    )
    assert [i.external_id for i in out] == ["a", "b", "c"]
    assert skipped == 2


def test_filter_new_items_respects_cache_eviction():
    seen_ids = set()
    seen_order = deque()
    first, _ = _filter_new_items(
        items=[_item("a"), _item("b"), _item("c")],
        seen_ids=seen_ids,
        seen_order=seen_order,
        max_cache_size=2,
    )
    assert [i.external_id for i in first] == ["a", "b", "c"]
    # "a" should have been evicted due to max_cache_size=2.
    second, skipped = _filter_new_items(
        items=[_item("a")],
        seen_ids=seen_ids,
        seen_order=seen_order,
        max_cache_size=2,
    )
    assert [i.external_id for i in second] == ["a"]
    assert skipped == 0
