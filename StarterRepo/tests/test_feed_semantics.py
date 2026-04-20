from datetime import datetime, timedelta
from types import SimpleNamespace

from newssentinel.api.main import _age_sec, _humanize_age, _live_sort_key


def test_humanize_age():
    assert _humanize_age(20) == "just now"
    assert _humanize_age(120) == "2 min ago"
    assert _humanize_age(7200) == "2 hr ago"
    assert _humanize_age(172800) == "2 day ago"
    assert _humanize_age(None) is None


def test_live_sort_prefers_published_freshness_then_lag():
    now = datetime.now()
    fresher = SimpleNamespace(
        published_at=now - timedelta(minutes=2),
        detected_at=now - timedelta(minutes=1),
        publication_lag_sec=60.0,
    )
    older = SimpleNamespace(
        published_at=now - timedelta(minutes=10),
        detected_at=now - timedelta(minutes=1),
        publication_lag_sec=60.0,
    )
    assert _live_sort_key(fresher, now) < _live_sort_key(older, now)


def test_age_sec_never_negative():
    now = datetime.now()
    future = now + timedelta(seconds=5)
    assert _age_sec(future, now) == 0.0
