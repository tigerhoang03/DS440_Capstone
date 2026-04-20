import asyncio
from datetime import datetime

from newssentinel.collectors import run
from newssentinel.models.schema import NormalizedItem, SourceType


def _item(external_id: str) -> NormalizedItem:
    return NormalizedItem(
        source="sched_test",
        source_type=SourceType.API,
        external_id=external_id,
        url=f"https://example.com/{external_id}",
        detected_at=datetime.now(),
        title=f"title-{external_id}",
    )


def test_interval_for_collector_uses_source_override(monkeypatch):
    monkeypatch.setattr(run.settings, "FINVIZ_NEWS_INTERVAL_SEC", 2.5)
    assert run._interval_for_collector("finviz_news", 9.0) == 2.5


def test_interval_for_collector_falls_back_when_invalid(monkeypatch):
    monkeypatch.setattr(run.settings, "FINVIZ_NEWS_INTERVAL_SEC", 0.0)
    assert run._interval_for_collector("finviz_news", 9.0) == 9.0
    assert run._interval_for_collector("unknown_collector", 9.0) == 9.0


def test_run_target_once_group_publishes_as_each_collector_finishes(monkeypatch):
    async def fake_collect_single_safe(collector_name: str):
        if collector_name == "slow":
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.01)
        return collector_name, [_item(collector_name)], None

    published_order: list[str] = []

    async def fake_publish_items(_redis, items):
        published_order.append(items[0].external_id)
        return len(items)

    class FakeRedis:
        async def aclose(self):
            return None

    monkeypatch.setitem(run.COLLECTOR_GROUPS, "test_group", ["slow", "fast"])
    monkeypatch.setattr(run, "_collect_single_safe", fake_collect_single_safe)
    monkeypatch.setattr(run, "publish_items", fake_publish_items)

    total = asyncio.run(run.run_target_once("test_group", FakeRedis()))
    assert total == 2
    assert published_order == ["fast", "slow"]


def test_run_group_independent_loops_uses_per_source_intervals(monkeypatch):
    captured: list[tuple[str, float, int]] = []

    async def fake_run_collector_loop(collector_name: str, interval_sec: float, max_runs: int):
        captured.append((collector_name, interval_sec, max_runs))

    monkeypatch.setattr(run, "run_collector_loop", fake_run_collector_loop)
    monkeypatch.setattr(run.settings, "WIRE_SITES_RSS_INTERVAL_SEC", 7.0)
    monkeypatch.setattr(run.settings, "FINVIZ_NEWS_INTERVAL_SEC", 2.0)
    monkeypatch.setattr(run.settings, "TRADINGVIEW_NEWS_INTERVAL_SEC", 3.0)

    asyncio.run(run.run_group_independent_loops("all_live_news", fallback_interval_sec=11.0, max_runs=4))

    by_collector = {name: (interval, runs) for name, interval, runs in captured}
    assert by_collector["wire_sites_rss"] == (7.0, 4)
    assert by_collector["finviz_news"] == (2.0, 4)
    assert by_collector["tradingview_news"] == (3.0, 4)
