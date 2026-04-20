from __future__ import annotations

import time

import altair as alt
import httpx
import pandas as pd
import streamlit as st

from newssentinel.dashboard.utils import (
    build_feed_table,
    compact_url,
    format_timestamp,
    get_or_set_session_started_at,
    sort_news_df,
)


st.set_page_config(page_title="NewsSentinel", layout="wide")


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #081018;
            --panel: #0f1b27;
            --panel-2: #132334;
            --border: rgba(153, 190, 255, 0.16);
            --text: #e9f3ff;
            --muted: #96a8bc;
            --accent: #27d3a7;
            --accent-soft: rgba(39, 211, 167, 0.12);
            --warn: #ffcc66;
        }
        .stApp {
            background:
                radial-gradient(circle at top right, rgba(39, 211, 167, 0.08), transparent 24%),
                linear-gradient(180deg, #071018 0%, #0a1320 100%);
            color: var(--text);
        }
        section[data-testid="stSidebar"] {
            background: rgba(10, 19, 32, 0.95);
            border-right: 1px solid var(--border);
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(17, 31, 46, 0.94), rgba(11, 20, 31, 0.94));
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 10px 12px;
            box-shadow: 0 10px 35px rgba(0, 0, 0, 0.16);
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-1px);
            border-color: rgba(39, 211, 167, 0.4);
            transition: transform 120ms ease, border-color 120ms ease;
        }
        .ns-hero {
            padding: 18px 20px 16px 20px;
            margin-bottom: 16px;
            border: 1px solid var(--border);
            border-radius: 18px;
            background: linear-gradient(135deg, rgba(12, 24, 38, 0.96), rgba(19, 35, 52, 0.92));
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.18);
        }
        .ns-title {
            font-size: 2.1rem;
            font-weight: 800;
            letter-spacing: 0.03em;
            margin: 0;
            color: var(--text);
        }
        .ns-subtitle {
            margin: 6px 0 0 0;
            color: var(--muted);
            font-size: 0.98rem;
        }
        .ns-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 14px;
        }
        .ns-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 10px;
            border-radius: 999px;
            background: var(--panel-2);
            border: 1px solid var(--border);
            color: var(--text);
            font-size: 0.82rem;
        }
        .ns-chip.live {
            background: var(--accent-soft);
            border-color: rgba(39, 211, 167, 0.35);
        }
        .ns-section {
            padding: 14px 16px;
            margin-bottom: 14px;
            border: 1px solid var(--border);
            border-radius: 18px;
            background: rgba(14, 27, 39, 0.86);
        }
        .ns-section h3 {
            margin: 0;
            font-size: 1rem;
            color: var(--text);
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }
        .ns-section p {
            margin: 6px 0 0 0;
            color: var(--muted);
            font-size: 0.9rem;
        }
        .ns-detail {
            padding: 16px;
            border: 1px solid var(--border);
            border-radius: 16px;
            background: linear-gradient(180deg, rgba(17, 31, 46, 0.96), rgba(12, 20, 30, 0.94));
        }
        .ns-detail:hover {
            border-color: rgba(39, 211, 167, 0.35);
            transition: border-color 120ms ease;
        }
        .ns-detail-title {
            margin: 0 0 10px 0;
            color: var(--text);
            font-size: 1.05rem;
            font-weight: 700;
        }
        .ns-badge-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 10px 0 12px 0;
        }
        .ns-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(39, 211, 167, 0.1);
            border: 1px solid rgba(39, 211, 167, 0.24);
            color: var(--text);
            font-size: 0.8rem;
        }
        .ns-meta {
            color: var(--muted);
            font-size: 0.87rem;
            margin: 4px 0;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            background: rgba(15, 27, 39, 0.85);
            border: 1px solid var(--border);
            border-radius: 12px 12px 0 0;
            color: var(--text);
            padding: 10px 16px;
        }
        .stTabs [aria-selected="true"] {
            background: rgba(39, 211, 167, 0.14) !important;
            border-color: rgba(39, 211, 167, 0.3) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def parse_datetime_col(df: pd.DataFrame, column: str) -> None:
    if column in df.columns:
        df[column] = pd.to_datetime(df[column], format="ISO8601", errors="coerce")


def fetch_news(api_base: str, **params):
    clean_params = {key: value for key, value in params.items() if value not in (None, "", [])}
    with httpx.Client(timeout=8) as client:
        response = client.get(f"{api_base}/news/latest", params=clean_params)
        response.raise_for_status()
        return response.json()


def fetch_source_lag(api_base: str, **params):
    clean_params = {key: value for key, value in params.items() if value not in (None, "", [])}
    with httpx.Client(timeout=8) as client:
        response = client.get(f"{api_base}/metrics/source-lag", params=clean_params)
        response.raise_for_status()
        return response.json()


def fetch_source_health(api_base: str, **params):
    clean_params = {key: value for key, value in params.items() if value not in (None, "", [])}
    with httpx.Client(timeout=8) as client:
        response = client.get(f"{api_base}/metrics/source-health", params=clean_params)
        response.raise_for_status()
        return response.json()


def prepare_news_df(records: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    if df.empty:
        return df
    parse_datetime_col(df, "detected_at")
    parse_datetime_col(df, "published_at")
    df = df.dropna(subset=["detected_at"]).copy()
    for column in ["publication_lag_sec", "detected_age_sec", "published_age_sec", "sentiment"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    if "publication_lag_sec" in df.columns:
        df["publication_lag_sec"] = df["publication_lag_sec"].clip(lower=0)
    return df


def prepare_health_df(records: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    if df.empty:
        return df
    parse_datetime_col(df, "latest_detected_at")
    parse_datetime_col(df, "latest_published_at")
    for column in [
        "total_items",
        "latest_detected_age_sec",
        "items_last_1m",
        "items_last_5m",
        "items_last_15m",
        "avg_lag_last_15m_sec",
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    if "avg_lag_last_15m_sec" in df.columns:
        df["avg_lag_last_15m_sec"] = df["avg_lag_last_15m_sec"].clip(lower=0)
    return df


def render_section_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="ns-section">
            <h3>{title}</h3>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_detail_panel(df: pd.DataFrame, key_prefix: str) -> None:
    if df.empty:
        return

    options = df["id"].tolist()
    selected_id = st.selectbox(
        "Inspect story",
        options=options,
        key=f"{key_prefix}_selected_id",
        format_func=lambda item_id: _format_story_option(df, item_id),
    )
    row = df.loc[df["id"] == selected_id].iloc[0]
    badge_html = "".join(
        [f'<span class="ns-badge">{label}</span>' for label in _detail_badges(row)]
    )
    summary = row.get("summary") or "No summary available."
    st.markdown(
        f"""
        <div class="ns-detail">
            <div class="ns-detail-title">{row.get("title") or "Untitled story"}</div>
            <div class="ns-badge-row">{badge_html}</div>
            <div class="ns-meta">Detected: {format_timestamp(row.get("detected_at"))}</div>
            <div class="ns-meta">Published: {format_timestamp(row.get("published_at"))}</div>
            <div class="ns-meta">Lag: {_format_lag(row.get("publication_lag_sec"))}</div>
            <div class="ns-meta">Link: <a href="{row.get("url") or "#"}" target="_blank">{compact_url(row.get("url"))}</a></div>
            <p style="margin-top:12px; color:#dce9f7;">{summary}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _detail_badges(row: pd.Series) -> list[str]:
    badges = [str(row.get("source") or "unknown")]
    tickers = row.get("tickers") or []
    badges.extend([str(ticker).upper() for ticker in tickers[:5]])
    sentiment_label = row.get("sentiment_label")
    if sentiment_label:
        badges.append(str(sentiment_label))
    sentiment = row.get("sentiment")
    if pd.notna(sentiment):
        badges.append(f"sentiment {float(sentiment):.2f}")
    sentiment_model = row.get("sentiment_model")
    if sentiment_model:
        badges.append(str(sentiment_model))
    return badges


def _format_lag(value) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "-"
    return _format_duration(float(numeric))


def _format_duration(seconds: float | int | None) -> str:
    numeric = pd.to_numeric(seconds, errors="coerce")
    if pd.isna(numeric):
        return "-"
    seconds_float = max(float(numeric), 0.0)
    if seconds_float < 60:
        return f"{seconds_float:.0f}s"
    if seconds_float < 3600:
        return f"{seconds_float / 60:.1f}m"
    if seconds_float < 86400:
        return f"{seconds_float / 3600:.1f}h"
    return f"{seconds_float / 86400:.1f}d"


def _format_story_option(df: pd.DataFrame, item_id: int) -> str:
    row = df.loc[df["id"] == item_id].iloc[0]
    source = row.get("source") or "source"
    title = row.get("title") or "Untitled story"
    return f"[{source}] {title[:90]}"


def render_feed_tab(df: pd.DataFrame, empty_message: str, key_prefix: str) -> None:
    if df.empty:
        st.info(empty_message)
        return
    table = build_feed_table(df)
    st.dataframe(table, width="stretch", hide_index=True, height=470)
    render_detail_panel(df, key_prefix)


def render_system_health_panel(health_df: pd.DataFrame) -> None:
    render_section_header(
        "System Health",
        "Session-scoped collector status from live Postgres detections and recent ingest activity.",
    )

    if health_df.empty:
        st.info("No source health data yet. Start collectors and the ingest worker to populate this panel.")
        return

    active_sources = int((health_df["status"] == "active").sum()) if "status" in health_df else 0
    quiet_sources = int((health_df["status"] == "quiet").sum()) if "status" in health_df else 0
    stale_sources = int((health_df["status"] == "stale").sum()) if "status" in health_df else 0
    latest_age = (
        health_df["latest_detected_age_sec"].dropna().min()
        if "latest_detected_age_sec" in health_df
        else None
    )
    items_last_1m = int(health_df["items_last_1m"].fillna(0).sum())
    items_last_5m = int(health_df["items_last_5m"].fillna(0).sum())
    items_last_15m = int(health_df["items_last_15m"].fillna(0).sum())

    h1, h2, h3, h4 = st.columns(4)
    with h1:
        st.metric("Active sources", active_sources, delta=f"{quiet_sources} quiet / {stale_sources} stale")
    with h2:
        st.metric("Ingest last 1m", items_last_1m)
    with h3:
        st.metric("Ingest last 5m", items_last_5m, delta=f"{items_last_15m} in 15m")
    with h4:
        st.metric("Latest detection", _format_duration(latest_age))

    table = pd.DataFrame(
        {
            "Source": health_df["source"],
            "Status": health_df["status"].astype(str).str.upper(),
            "Latest detected": health_df["latest_detected_recency"].fillna("-"),
            "Ingest age": health_df["latest_detected_age_sec"].apply(_format_duration),
            "Last 1m": health_df["items_last_1m"].fillna(0).astype(int),
            "Last 5m": health_df["items_last_5m"].fillna(0).astype(int),
            "Last 15m": health_df["items_last_15m"].fillna(0).astype(int),
            "Avg lag 15m": health_df["avg_lag_last_15m_sec"].apply(_format_duration),
            "Total": health_df["total_items"].fillna(0).astype(int),
        }
    )
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        height=min(280, 60 + 36 * max(len(table), 1)),
    )


def render_metrics_tab(news_df: pd.DataFrame, lag_df: pd.DataFrame, health_df: pd.DataFrame) -> None:
    render_section_header(
        "Source Metrics",
        "Session-scoped latency, sentiment, and throughput for live rows only.",
    )
    render_system_health_panel(health_df)

    if not lag_df.empty:
        for column in ["avg_publication_lag_sec", "min_publication_lag_sec", "max_publication_lag_sec"]:
            if column in lag_df.columns:
                lag_df[column] = pd.to_numeric(lag_df[column], errors="coerce")
                lag_df[column] = lag_df[column].clip(lower=0)
        lag_df = lag_df.dropna(subset=["avg_publication_lag_sec"]).sort_values("avg_publication_lag_sec")

    k1, k2, k3 = st.columns(3)
    if lag_df.empty:
        with k1:
            st.metric("Fastest source", "-")
        with k2:
            st.metric("Slowest source", "-")
        with k3:
            st.metric("Avg lag", "-")
        st.info(
            "Session lag metrics will appear once live rows arrive after this dashboard session starts."
        )
    else:
        with k1:
            st.metric("Fastest source", str(lag_df.iloc[0]["source"]))
        with k2:
            st.metric("Slowest source", str(lag_df.iloc[-1]["source"]))
        with k3:
            st.metric("Avg lag", f"{float(lag_df['avg_publication_lag_sec'].mean()):.1f} sec")
        lag_plot = lag_df.rename(
            columns={
                "avg_publication_lag_sec": "Average lag (sec)",
                "min_publication_lag_sec": "Best lag (sec)",
                "max_publication_lag_sec": "Worst lag (sec)",
                "item_count": "Rows",
                "source": "Source",
            }
        )
        lag_chart = (
            alt.Chart(lag_plot)
            .mark_bar(cornerRadiusEnd=5)
            .encode(
                x=alt.X("Average lag (sec):Q", title="Average publication lag"),
                y=alt.Y("Source:N", sort="x", title=None),
                color=alt.Color("Source:N", legend=None, scale=alt.Scale(scheme="tealblues")),
                tooltip=[
                    alt.Tooltip("Source:N"),
                    alt.Tooltip("Rows:Q", format=","),
                    alt.Tooltip("Average lag (sec):Q", format=",.1f"),
                    alt.Tooltip("Best lag (sec):Q", format=",.1f"),
                    alt.Tooltip("Worst lag (sec):Q", format=",.1f"),
                ],
            )
            .properties(height=max(220, 42 * len(lag_plot)))
        )
        st.altair_chart(lag_chart, width="stretch")
        lag_table = lag_df[
            [
                "source",
                "item_count",
                "avg_publication_lag_sec",
                "min_publication_lag_sec",
                "max_publication_lag_sec",
            ]
        ].copy()
        lag_table.columns = ["Source", "Rows", "Avg lag", "Best lag", "Worst lag"]
        for column in ["Avg lag", "Best lag", "Worst lag"]:
            lag_table[column] = lag_table[column].apply(_format_duration)
        st.dataframe(
            lag_table,
            width="stretch",
            hide_index=True,
            height=260,
        )

    if news_df.empty:
        st.info("No recent news rows available for charting yet.")
        return

    chart_df = news_df.sort_values("detected_at", ascending=False).copy()
    c1, c2 = st.columns([2, 1])
    with c1:
        render_section_header("Sentiment Trend", "Average sentiment by detected time.")
        sentiment_df = chart_df.dropna(subset=["sentiment"]).copy()
        if sentiment_df.empty:
            st.info("No sentiment values available yet.")
        else:
            sentiment_df = (
                sentiment_df.set_index("detected_at")
                .resample("1min")["sentiment"]
                .mean()
                .reset_index()
                .dropna()
            )
            sentiment_chart = (
                alt.Chart(sentiment_df)
                .mark_line(point=True, color="#27d3a7")
                .encode(
                    x=alt.X("detected_at:T", title="Detected minute"),
                    y=alt.Y("sentiment:Q", title="Avg sentiment", scale=alt.Scale(domain=[-1, 1])),
                    tooltip=[
                        alt.Tooltip("detected_at:T", title="Minute"),
                        alt.Tooltip("sentiment:Q", title="Avg sentiment", format=".3f"),
                    ],
                )
                .properties(height=260)
            )
            st.altair_chart(sentiment_chart, width="stretch")
    with c2:
        render_section_header("Item Throughput", "Detected item count by minute.")
        count_df = chart_df[["detected_at", "source"]].copy()
        count_df["count"] = 1
        count_df = (
            count_df.groupby([pd.Grouper(key="detected_at", freq="1min"), "source"])["count"]
            .sum()
            .reset_index()
        )
        throughput_chart = (
            alt.Chart(count_df)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("detected_at:T", title="Detected minute"),
                y=alt.Y("count:Q", title="Items"),
                color=alt.Color("source:N", title="Source", scale=alt.Scale(scheme="tableau20")),
                tooltip=[
                    alt.Tooltip("detected_at:T", title="Minute"),
                    alt.Tooltip("source:N", title="Source"),
                    alt.Tooltip("count:Q", title="Items", format=","),
                ],
            )
            .properties(height=260)
        )
        st.altair_chart(throughput_chart, width="stretch")


inject_styles()

api_base = st.sidebar.text_input("API Base URL", "http://localhost:8000")
refresh = st.sidebar.slider("Refresh (sec)", 1, 20, 5, 1)
auto = st.sidebar.toggle("Auto-refresh", True)
global_source = st.sidebar.text_input("Source filter", "")
global_limit = st.sidebar.slider("Default rows", 50, 500, 150, 25)

session_started_at = get_or_set_session_started_at(st.session_state)
session_started_at_iso = session_started_at.isoformat()

st.markdown(
    f"""
    <div class="ns-hero">
        <h1 class="ns-title">NewsSentinel</h1>
        <p class="ns-subtitle">Live market news intelligence</p>
        <div class="ns-chip-row">
            <span class="ns-chip live">Auto-refresh {"ON" if auto else "OFF"}</span>
            <span class="ns-chip">Refresh {refresh}s</span>
            <span class="ns-chip">Session start {session_started_at.strftime("%Y-%m-%d %H:%M:%S UTC")}</span>
            <span class="ns-chip">API {api_base}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

live_records = fetch_news(
    api_base,
    limit=global_limit,
    source=global_source.strip() or None,
    detected_after=session_started_at_iso,
    rank_mode="detected",
    dedup=True,
)
archive_records = fetch_news(
    api_base,
    limit=global_limit,
    source=global_source.strip() or None,
    detected_before=session_started_at_iso,
    rank_mode="detected",
    dedup=True,
)
metrics_records = fetch_news(
    api_base,
    limit=max(global_limit, 250),
    source=global_source.strip() or None,
    rank_mode="detected",
    dedup=True,
)
lag_records = fetch_source_lag(
    api_base,
    source=global_source.strip() or None,
    detected_after=session_started_at_iso,
)
health_records = fetch_source_health(
    api_base,
    source=global_source.strip() or None,
    detected_after=session_started_at_iso,
)

live_df = prepare_news_df(live_records)
archive_df = prepare_news_df(archive_records)
metrics_df = prepare_news_df(metrics_records)
lag_df = pd.DataFrame(lag_records)
health_df = prepare_health_df(health_records)

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Live items", len(live_df))
with k2:
    st.metric("Archive items", len(archive_df))
with k3:
    st.metric("Sources", int(metrics_df["source"].nunique()) if not metrics_df.empty else 0)
with k4:
    avg_sentiment = metrics_df["sentiment"].dropna().mean() if "sentiment" in metrics_df and not metrics_df.empty else None
    st.metric("Avg sentiment", f"{float(avg_sentiment):.3f}" if avg_sentiment is not None and pd.notna(avg_sentiment) else "-")

live_tab, search_tab, metrics_tab, archive_tab = st.tabs(
    ["Live Feed", "Search / Explore", "Source Metrics", "Archive"]
)

with live_tab:
    render_section_header(
        "Live Feed",
        "Fresh session-only stories detected after this dashboard session started.",
    )
    render_feed_tab(
        sort_news_df(live_df),
        "No live stories have been detected since this dashboard session started.",
        "live_feed",
    )

with search_tab:
    render_section_header(
        "Search / Explore",
        "Filter the newest rows by ticker tags and exact headline keyword patterns.",
    )
    s0, s1, s2, s3, s4 = st.columns([1.2, 1.4, 1.0, 0.9, 0.9])
    with s0:
        ticker_search = st.text_input(
            "Ticker",
            placeholder="TSLA, AAPL, NVDA",
            key="ticker_search",
        )
    with s1:
        keyword_search = st.text_input(
            "Headline keyword",
            placeholder="revenue, guidance, merger",
            key="keyword_search",
        )
    with s2:
        search_source = st.text_input("Source", value=global_source, key="search_source")
    with s3:
        search_rank_mode = st.selectbox("Sort", ["live", "detected"], index=0)
    with s4:
        search_dedup = st.toggle("Dedup", value=True)

    s5 = st.columns([1.0])[0]
    with s5:
        search_limit = st.slider("Rows", 50, 500, global_limit, 25, key="search_limit")

    ticker_query = ticker_search.strip().upper() or None
    keyword_query = keyword_search.strip() or None
    search_records = fetch_news(
        api_base,
        limit=search_limit,
        source=search_source.strip() or None,
        tickers=ticker_query,
        headline_keyword=keyword_query,
        dedup=search_dedup,
        rank_mode=search_rank_mode,
    )
    search_df = prepare_news_df(search_records)
    search_empty_message = (
        "No matches found."
        if ticker_query or keyword_query
        else "Enter a ticker and/or headline keyword to filter the newest rows in scope."
    )
    render_feed_tab(
        search_df,
        search_empty_message,
        "search_feed",
    )

with metrics_tab:
    render_metrics_tab(metrics_df, lag_df, health_df)

with archive_tab:
    render_section_header(
        "Archive",
        "Stories detected before the current dashboard session boundary.",
    )
    render_feed_tab(
        sort_news_df(archive_df),
        "No archived stories are available before this session boundary.",
        "archive_feed",
    )

if auto:
    time.sleep(refresh)
    st.rerun()
