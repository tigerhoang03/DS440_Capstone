import time
import pandas as pd
import streamlit as st
import httpx

API_BASE = st.sidebar.text_input("API Base URL", "http://localhost:8000")

st.set_page_config(page_title="NewsSentinel", layout="wide")
st.title("NewsSentinel — Live News + Sentiment")

col1, col2, col3 = st.columns([2,1,1])
limit = col2.slider("Rows", 50, 500, 200, 50)
source = col3.text_input("Source filter (optional)", "")
rank_mode = st.sidebar.selectbox(
    "Feed ranking",
    options=["live", "detected"],
    index=0,
    help="live: published freshness + lag, detected: newest detected first",
)

refresh = st.sidebar.slider("Refresh (sec)", 1, 20, 5, 1)
auto = st.sidebar.toggle("Auto-refresh", True)


def parse_datetime_col(df: pd.DataFrame, column: str) -> None:
    if column in df.columns:
        # Mixed ISO strings can include optional fractional seconds.
        df[column] = pd.to_datetime(df[column], format="ISO8601", errors="coerce")


def fetch():
    params = {"limit": limit, "rank_mode": rank_mode}
    if source.strip():
        params["source"] = source.strip()
    with httpx.Client(timeout=5) as client:
        r = client.get(f"{API_BASE}/news/latest", params=params)
        r.raise_for_status()
        return r.json()

def fetch_source_lag():
    params = {}
    if source.strip():
        params["source"] = source.strip()
    with httpx.Client(timeout=5) as client:
        r = client.get(f"{API_BASE}/metrics/source-lag", params=params)
        r.raise_for_status()
        return r.json()


data = fetch()
lag_data = fetch_source_lag()
df = pd.DataFrame(data)
lag_df = pd.DataFrame(lag_data)
if not df.empty:
    parse_datetime_col(df, "detected_at")
    parse_datetime_col(df, "published_at")
    df = df.dropna(subset=["detected_at"])
    for col in ["publication_lag_sec", "detected_age_sec", "published_age_sec"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    feed_df = df.copy()
    chart_df = df.sort_values("detected_at", ascending=False).copy()

    # KPIs
    with col1:
        st.metric("Items (latest)", len(feed_df))
    with col2:
        st.metric(
            "Avg sentiment",
            round(float(feed_df["sentiment"].dropna().mean()) if "sentiment" in feed_df else 0.0, 3),
        )
    with col3:
        st.metric("Sources", feed_df["source"].nunique())

    k1, k2 = st.columns([1, 1])
    with k1:
        if "detected_recency" in feed_df.columns:
            st.metric("Top detected recency", str(feed_df.iloc[0]["detected_recency"]))
    with k2:
        if "published_recency" in feed_df.columns:
            st.metric("Top published recency", str(feed_df.iloc[0]["published_recency"]))

    # chart: sentiment over time (detected)
    c1, c2 = st.columns([2,1])
    with c1:
        tmp = chart_df.dropna(subset=["sentiment"]).copy()
        if not tmp.empty:
            tmp = tmp.set_index("detected_at").resample("1min")["sentiment"].mean().reset_index()
            st.line_chart(tmp, x="detected_at", y="sentiment")
        else:
            st.info("No sentiment values yet.")
    with c2:
        tmp = chart_df.copy()
        tmp["count"] = 1
        tmp = tmp.set_index("detected_at").resample("1min")["count"].sum().reset_index()
        st.line_chart(tmp, x="detected_at", y="count")

    st.subheader("Source Lag (seconds)")
    if not lag_df.empty:
        lag_cols = [
            "avg_publication_lag_sec",
            "min_publication_lag_sec",
            "max_publication_lag_sec",
        ]
        for col in lag_cols:
            if col in lag_df.columns:
                lag_df[col] = pd.to_numeric(lag_df[col], errors="coerce")
        lag_df = lag_df.dropna(subset=["avg_publication_lag_sec"])
        if lag_df.empty:
            st.info("Lag metrics not available yet. Collect more items with published timestamps.")
        else:
            lag_df = lag_df.sort_values("avg_publication_lag_sec", ascending=True)

            l1, l2, l3 = st.columns([1, 1, 1])
            with l1:
                st.metric("Fastest source", lag_df.iloc[0]["source"])
            with l2:
                st.metric("Slowest source", lag_df.iloc[-1]["source"])
            with l3:
                st.metric("Avg lag (all shown)", round(float(lag_df["avg_publication_lag_sec"].mean()), 2))

            st.bar_chart(lag_df, x="source", y="avg_publication_lag_sec")
            st.dataframe(
                lag_df[
                    [
                        "source",
                        "item_count",
                        "avg_publication_lag_sec",
                        "min_publication_lag_sec",
                        "max_publication_lag_sec",
                    ]
                ],
                use_container_width=True,
                height=260,
            )
    else:
        st.info("Lag metrics not available yet. Collect more items with published timestamps.")

    st.subheader("Live feed")
    display_cols = [
        "detected_recency",
        "published_recency",
        "publication_lag_sec",
        "detected_at",
        "published_at",
        "source",
        "tickers",
        "sentiment",
        "title",
        "summary",
        "url",
    ]
    display_cols = [c for c in display_cols if c in feed_df.columns]
    st.dataframe(
        feed_df[display_cols],
        use_container_width=True,
        height=650,
    )
else:
    st.warning("No data yet. Run a collector and the ingest worker.")

if auto:
    time.sleep(refresh)
    st.rerun()
