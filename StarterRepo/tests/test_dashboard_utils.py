from datetime import datetime

import pandas as pd

from newssentinel.dashboard.utils import get_or_set_session_started_at, looks_like_ticker_query, sort_news_df


def test_get_or_set_session_started_at_sets_once_and_reuses_value():
    session_state = {}
    now = datetime(2026, 4, 13, 12, 0, 0)
    first = get_or_set_session_started_at(session_state, now=now)
    second = get_or_set_session_started_at(session_state, now=datetime(2026, 4, 13, 13, 0, 0))

    assert first == now
    assert second == now
    assert session_state["session_started_at"] == now.isoformat()


def test_looks_like_ticker_query():
    assert looks_like_ticker_query("TSLA") is True
    assert looks_like_ticker_query("BRK.B") is True
    assert looks_like_ticker_query("apple earnings") is False


def test_sort_news_df_handles_empty_dataframe_without_detected_at():
    df = pd.DataFrame()
    out = sort_news_df(df)
    assert out.empty
