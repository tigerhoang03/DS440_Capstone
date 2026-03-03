import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Stocks Dashboard", layout="wide")

# ---------- CSS (cards / dark UI) ----------
st.markdown(
    """
    <style>
      .app-bg {
        background: radial-gradient(1200px 800px at 20% 0%, #0b1b33 0%, #05070c 60%);
        padding: 0.5rem 0.75rem 1.25rem 0.75rem;
      }

      .card {
        background: rgba(14, 23, 40, 0.92);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: 16px 16px 14px 16px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.45);
      }

      .card-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: rgba(255,255,255,0.92);
        display: flex;
        gap: 10px;
        align-items: center;
        margin-bottom: 10px;
      }

      .muted { color: rgba(255,255,255,0.55); font-size: 0.9rem; }
      .big   { font-size: 2.2rem; font-weight: 800; color: rgba(255,255,255,0.95); }
      .pos   { color: #22c55e; font-weight: 700; }
      .neg   { color: #ef4444; font-weight: 700; }

      .divider { height: 1px; background: rgba(255,255,255,0.06); margin: 12px 0; }

      .pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        background: rgba(34,197,94,0.15);
        color: #22c55e;
        border: 1px solid rgba(34,197,94,0.25);
        margin-left: 8px;
      }

      .news-item { padding: 10px 0; border-left: 3px solid #3b82f6; padding-left: 12px; }
      .news-head { color: rgba(255,255,255,0.9); font-weight: 700; }
      .news-sub  { color: rgba(255,255,255,0.55); font-size: 0.85rem; margin-top: 4px; }

      /* Make Streamlit containers blend into our background */
      section[data-testid="stAppViewContainer"] { background: transparent; }
      header[data-testid="stHeader"] { background: transparent; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Wrapper background
st.markdown('<div class="app-bg">', unsafe_allow_html=True)

# ---------- Mock DataFrames (replace with your real ones) ----------
metricsDf = pd.DataFrame([{
    "ticker": "AAPL",
    "price": 178.45,
    "change": 2.34,
    "pct_change": 1.33,
    "volume": "52.3M",
    "market_cap": "2.8T",
    "pe": 29.5,
    "range_52w": "$120 - $195",
    "avg_volume": "45.2M",
    "div_yield": "0.52%",
}])

newsDf = pd.DataFrame([
    {"title": "Apple announces new AI features for iOS", "source": "Tech News", "age": "2h ago", "sentiment": "positive"},
    {"title": "Apple suppliers report strong Q1 earnings", "source": "Market Watch", "age": "5h ago", "sentiment": "positive"},
])

marketDf = pd.DataFrame([
    {"name": "S&P 500", "value": 5234.56, "pct": 0.85},
    {"name": "NASDAQ", "value": 16789.23, "pct": 1.12},
    {"name": "DOW", "value": 38456.12, "pct": -0.23},
])

watchlistDf = pd.DataFrame([
    {"ticker": "AAPL", "price": 178.45, "pct": 1.33},
    {"ticker": "TSLA", "price": 245.67, "pct": -2.08},
    {"ticker": "GOOGL", "price": 142.89, "pct": 0.41},
])

sentDf = pd.DataFrame({
    "date": pd.date_range("2026-01-31", periods=8),
    "sentiment": [65, 67, 70, 68, 73, 76, 75, 78],
})

# ---------- Top search bar ----------
st.text_input(" ", placeholder="Search stocks, news, or market data...", label_visibility="collapsed")

# ---------- Layout: left / center / right ----------
leftCol, centerCol, rightCol = st.columns([1.1, 3.2, 1.3], gap="large")

# ---------- Helpers ----------
def card_open(title: str):
    st.markdown(f"""
      <div class="card">
        <div class="card-title"> {title}</div>
    """, unsafe_allow_html=True)

def card_close():
    st.markdown("</div>", unsafe_allow_html=True)

def fmt_pct(x: float):
    cls = "pos" if x >= 0 else "neg"
    sign = "+" if x >= 0 else ""
    return f'<span class="{cls}">{sign}{x:.2f}%</span>'

# ---------- Left: Stock Metrics card ----------
with leftCol:
    m = metricsDf.iloc[0]

    card_open("Stock Metrics")
    st.markdown(f"""
      <div class="muted">{m['ticker']}</div>
      <div class="big">${m['price']:.2f}</div>
      <div class="pos">↗ +{m['change']:.2f} (+{m['pct_change']:.2f}%)</div>
      <div class="muted">Apple Inc.</div>
      <div class="divider"></div>

      <div class="muted">Volume</div><div style="color:white;font-weight:800;font-size:1.2rem;">{m['volume']}</div>
      <div class="divider"></div>

      <div class="muted">Market Cap</div><div style="color:white;font-weight:800;font-size:1.2rem;">{m['market_cap']}</div>
      <div class="divider"></div>

      <div class="muted">P/E Ratio</div><div style="color:white;font-weight:800;font-size:1.2rem;">{m['pe']}</div>
      <div class="divider"></div>

      <div class="muted">52W Range</div><div style="color:white;font-weight:800;font-size:1.2rem;">{m['range_52w']}</div>
      <div class="divider"></div>

      <div class="muted">Avg Volume</div><div style="color:white;font-weight:800;font-size:1.2rem;">{m['avg_volume']}</div>
      <div class="divider"></div>

      <div class="muted">Dividend Yield</div><div style="color:white;font-weight:800;font-size:1.2rem;">{m['div_yield']}</div>
    """, unsafe_allow_html=True)
    card_close()

# ---------- Center: Latest News card + Sentiment Analysis big card ----------
with centerCol:
    # Latest News
    card_open("Latest News")
    for _, r in newsDf.iterrows():
        pill = '<span class="pill">positive</span>' if r["sentiment"] == "positive" else ""
        st.markdown(f"""
          <div class="news-item">
            <div class="news-head">{r['title']}</div>
            <div class="news-sub">{r['source']} &nbsp; • &nbsp; {r['age']} {pill}</div>
          </div>
        """, unsafe_allow_html=True)
    card_close()

    st.write("")  # spacing

    # Sentiment Analysis (chart card)
    card_open("Sentiment Analysis")

    topRowL, topRowR = st.columns([2, 1])
    with topRowL:
        st.markdown('<div class="big" style="font-size:2.0rem;">80 <span class="pos" style="font-size:1.1rem;">Very Positive</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="muted">Current sentiment score for Apple Inc.</div>', unsafe_allow_html=True)
    with topRowR:
        st.selectbox("Select Stock:", ["AAPL", "TSLA", "GOOGL"], index=0)

    fig = px.line(sentDf, x="date", y="sentiment", markers=True)
    fig.update_layout(
        height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="rgba(255,255,255,0.75)",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", range=[0, 100])

    st.plotly_chart(fig,
                width='stretch')
    card_close()

# ---------- Right: Market card + Watchlist card ----------
with rightCol:
    # Market
    card_open("Market")
    st.markdown('<div class="muted" style="margin-bottom:8px;">Indices</div>', unsafe_allow_html=True)
    for _, r in marketDf.iterrows():
        cls = "pos" if r["pct"] >= 0 else "neg"
        arrow = "↗" if r["pct"] >= 0 else "↘"
        st.markdown(f"""
          <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06);
                      border-radius: 14px; padding: 12px; margin-bottom: 10px;">
            <div class="muted">{r['name']}</div>
            <div style="display:flex;justify-content:space-between;align-items:baseline;">
              <div style="color:white;font-weight:800;font-size:1.2rem;">{r['value']:,.2f}</div>
              <div class="{cls}" style="font-weight:800;">{arrow} {r['pct']:+.2f}%</div>
            </div>
          </div>
        """, unsafe_allow_html=True)
    card_close()

    st.write("")

    # Watchlist
    card_open("Watchlist")
    for _, r in watchlistDf.iterrows():
        cls = "pos" if r["pct"] >= 0 else "neg"
        st.markdown(f"""
          <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06);
                      border-radius: 14px; padding: 12px; margin-bottom: 10px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <div style="color:white;font-weight:900;">{r['ticker']}</div>
              <div class="{cls}" style="font-weight:800;">{r['pct']:+.2f}%</div>
            </div>
            <div class="muted">${r['price']:.2f}</div>
          </div>
        """, unsafe_allow_html=True)
    card_close()

st.markdown("</div>", unsafe_allow_html=True)  # close app-bg