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

refresh = st.sidebar.slider("Refresh (sec)", 1, 20, 5, 1)
auto = st.sidebar.toggle("Auto-refresh", True)


def parse_datetime_col(df: pd.DataFrame, column: str) -> None:
    if column in df.columns:
        # Mixed ISO strings can include optional fractional seconds.
        df[column] = pd.to_datetime(df[column], format="ISO8601", errors="coerce")


def fetch():
    params = {"limit": limit}
    if source.strip():
        params["source"] = source.strip()
    with httpx.Client(timeout=5) as client:
        r = client.get(f"{API_BASE}/news/latest", params=params)
        r.raise_for_status()
        return r.json()

data = fetch()
df = pd.DataFrame(data)
if not df.empty:
    parse_datetime_col(df, "detected_at")
    parse_datetime_col(df, "published_at")
    df = df.dropna(subset=["detected_at"])
    df = df.sort_values("detected_at", ascending=False)

    # KPIs
    with col1:
        st.metric("Items (latest)", len(df))
    with col2:
        st.metric("Avg sentiment", round(float(df["sentiment"].dropna().mean()) if "sentiment" in df else 0.0, 3))
    with col3:
        st.metric("Sources", df["source"].nunique())

    # chart: sentiment over time (detected)
    c1, c2 = st.columns([2,1])
    with c1:
        tmp = df.dropna(subset=["sentiment"]).copy()
        if not tmp.empty:
            tmp = tmp.set_index("detected_at").resample("1min")["sentiment"].mean().reset_index()
            st.line_chart(tmp, x="detected_at", y="sentiment")
        else:
            st.info("No sentiment values yet.")
    with c2:
        tmp = df.copy()
        tmp["count"] = 1
        tmp = tmp.set_index("detected_at").resample("1min")["count"].sum().reset_index()
        st.line_chart(tmp, x="detected_at", y="count")

    st.subheader("Live feed")
    display_cols = ["detected_at", "source", "tickers", "sentiment", "title", "summary", "url"]
    if "published_at" in df.columns:
        display_cols.insert(1, "published_at")
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        height=650,
    )
else:
    st.warning("No data yet. Run a collector and the ingest worker.")

if auto:
    time.sleep(refresh)
    st.rerun()
