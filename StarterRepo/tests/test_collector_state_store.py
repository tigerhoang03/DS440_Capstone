import asyncio
from collections import deque
from datetime import datetime

from newssentinel.collectors import run
from newssentinel.collectors.state_store import load_collector_seen_cache, save_collector_seen_cache
from newssentinel.models.schema import NormalizedItem, SourceType


def _item(external_id: str) -> NormalizedItem:
    return NormalizedItem(
        source="state_test",
        source_type=SourceType.API,
        external_id=external_id,
        url=f"https://example.com/{external_id}",
        detected_at=datetime.now(),
        title=f"title-{external_id}",
    )


def test_state_store_roundtrip(tmp_path):
    collector_name = "roundtrip"
    save_collector_seen_cache(
        collector_name=collector_name,
        seen_order=deque(["a", "b", "c"]),
        state_dir=str(tmp_path),
        max_cache_size=10,
    )

    seen_ids, seen_order = load_collector_seen_cache(
        collector_name=collector_name,
        state_dir=str(tmp_path),
        max_cache_size=10,
    )
    assert seen_ids == {"a", "b", "c"}
    assert list(seen_order) == ["a", "b", "c"]


def test_get_collector_instance_loads_seen_cache_from_state(tmp_path, monkeypatch):
    collector_name = "dummy_state_collector"
    save_collector_seen_cache(
        collector_name=collector_name,
        seen_order=deque(["x", "y"]),
        state_dir=str(tmp_path),
        max_cache_size=10,
    )

    monkeypatch.setitem(run.COLLECTORS, collector_name, lambda: object())
    monkeypatch.setattr(run.settings, "COLLECTOR_STATE_ENABLED", True)
    monkeypatch.setattr(run.settings, "COLLECTOR_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(run.settings, "COLLECTOR_DELTA_CACHE_SIZE", 10)

    run._collector_instances.clear()
    run._collector_seen_ids.clear()
    run._collector_seen_order.clear()

    _ = run._get_collector_instance(collector_name)
    assert run._collector_seen_ids[collector_name] == {"x", "y"}
    assert list(run._collector_seen_order[collector_name]) == ["x", "y"]


def test_collect_single_persists_only_on_new_items(tmp_path, monkeypatch):
    collector_name = "dummy_collect_single"

    class DummyCollector:
        async def collect(self):
            return [_item("same-id")]

    save_calls: list[int] = []

    def fake_save(**kwargs):
        save_calls.append(len(kwargs["seen_order"]))

    monkeypatch.setitem(run.COLLECTORS, collector_name, lambda: DummyCollector())
    monkeypatch.setattr(run, "save_collector_seen_cache", fake_save)
    monkeypatch.setattr(run.settings, "COLLECTOR_STATE_ENABLED", True)
    monkeypatch.setattr(run.settings, "COLLECTOR_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(run.settings, "COLLECTOR_DELTA_CACHE_SIZE", 10)

    run._collector_instances.clear()
    run._collector_seen_ids.clear()
    run._collector_seen_order.clear()

    _, first = asyncio.run(run.collect_single(collector_name))
    _, second = asyncio.run(run.collect_single(collector_name))

    assert len(first) == 1
    assert len(second) == 0
    assert save_calls == [1]
