# ================================================================
# QuantFX Terminal — Web Edition (Deploy‑Ready Streamlit Version)
# ================================================================

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf

import indicators as ind

# ================================================================
# TELEGRAM CONFIG (Cloud‑Safe Storage)
# ================================================================

CONFIG_DIR = Path("./config")
CONFIG_DIR.mkdir(exist_ok=True)
TELEGRAM_CONFIG_FILE = CONFIG_DIR / "telegram_config.json"

def load_saved_telegram_config():
    try:
        data = json.loads(TELEGRAM_CONFIG_FILE.read_text())
        return data.get("token", ""), data.get("chat_id", "")
    except Exception:
        return "", ""

def save_telegram_config(token, chat_id):
    TELEGRAM_CONFIG_FILE.write_text(json.dumps({"token": token, "chat_id": chat_id}))

# ================================================================
# THEME
# ================================================================

COLOR_BG_DARK = "#0B0E11"
COLOR_PANEL_BG = "#11151C"
COLOR_TEXT_MAIN = "#E5E9F0"
COLOR_TEXT_MUTED = "#9FA8C3"
COLOR_BULL = "#26FF9A"
COLOR_BEAR = "#FF4F7B"
COLOR_GREEN = "#00FF66"
COLOR_RED = "#FF3333"
COLOR_MA9 = "#00FF66"
COLOR_MA20 = "#FF3333"
COLOR_MACD_LINE = "#00FFCC"
COLOR_SIGNAL_LINE = "#FF66CC"
COLOR_ZERO_LINE = "#4C566A"

st.set_page_config(page_title="QuantFX Terminal", layout="wide")

st.markdown(
    f"""
<style>
.stApp {{ background-color: {COLOR_BG_DARK}; color: {COLOR_TEXT_MAIN}; }}
section[data-testid="stSidebar"] {{ background-color: {COLOR_PANEL_BG}; }}
.outlook-box {{
    background-color: {COLOR_PANEL_BG};
    border: 1px solid #202635;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 12px;
}}
.news-card {{
    background-color: {COLOR_PANEL_BG};
    border: 1px solid #202635;
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 8px;
}}
</style>
""",
    unsafe_allow_html=True,
)

# ================================================================
# SYMBOL UNIVERSE
# ================================================================

COMMODITIES = [
    ("GC=F", "GOLD"), ("SI=F", "SILVER"), ("KC=F", "COFFEE"),
    ("CL=F", "CRUDE"), ("NG=F", "GAS")
]

FOREX = [
    ("EURUSD=X", "EUR/USD"), ("GBPUSD=X", "GBP/USD"),
    ("USDJPY=X", "USD/JPY"), ("AUDUSD=X", "AUD/USD"),
    ("USDCAD=X", "USD/CAD")
]

TIMEFRAMES = {
    "15m (1 week)": ("15m", "5d"),
    "1h (1 month)": ("1h", "1mo"),
    "4h (3 months)": ("1h", "3mo"),
    "1d (1 year)": ("1d", "1y"),
    "1wk (5 years)": ("1wk", "5y"),
}

# ================================================================
# SESSION STATE INIT
# ================================================================

if "telegram_token" not in st.session_state:
    saved_token, saved_chat_id = load_saved_telegram_config()
    st.session_state.telegram_token = saved_token
    st.session_state.telegram_chat_id = saved_chat_id

# ================================================================
# CACHED FETCHERS
# ================================================================

@st.cache_data(ttl=60)
def cached_ohlc(symbol, period, interval):
    return ind.fetch_live_ohlc(symbol, period=period, interval=interval)

@st.cache_data(ttl=60)
def cached_outlook(symbol, display, period, interval):
    return ind.compute_7day_outlook(symbol, display, period=period, interval=interval)

@st.cache_data(ttl=300)
def cached_news(symbol):
    try:
        t = yf.Ticker(symbol)
        return t.news if hasattr(t, "news") else []
    except Exception:
        return []

@st.cache_data(ttl=300)
def cached_filtered_top5_charts():
    qualified = []
    us_yf = getattr(ind, "us100_yf", ["AAPL","MSFT","NVDA","AMZN","META"])[:5]
    us_raw = getattr(ind, "us100_raw", ["AAPL","MSFT","NVDA","AMZN","META"])[:5]
    nifty_yf = getattr(ind, "nifty200_yf", ["RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS"])[:5]
    nifty_raw = getattr(ind, "nifty200_raw", ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK"])[:5]

    universe = list(zip(us_yf, us_raw)) + list(zip(nifty_yf, nifty_raw))

    for yf_sym, disp in universe:
        r = ind.evaluate_oracle_score(yf_sym, display=disp)
        if r:
            try:
                score = float(str(r["Score"]).replace("%",""))
                tp1 = float(str(r["TP1_PCT"]).replace("%",""))
                if r["Signal"].upper()=="BUY" and score>=50 and tp1>=5:
                    qualified.append(r)
            except:
                pass
    return qualified

@st.cache_data(ttl=300)
def cached_top5_scan():
    us100_top5_res, nifty_top5_res = [], []
    us_yf = getattr(ind,"us100_yf",["AAPL","MSFT","NVDA","AMZN","META"])[:5]
    us_raw = getattr(ind,"us100_raw",["AAPL","MSFT","NVDA","AMZN","META"])[:5]
    nifty_yf = getattr(ind,"nifty200_yf",["RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS"])[:5]
    nifty_raw = getattr(ind,"nifty200_raw",["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK"])[:5]

    for yf_sym, disp in zip(us_yf, us_raw):
        r = ind.evaluate_oracle_score(yf_sym, display=disp)
        if r: us100_top5_res.append(r)

    for yf_sym, disp in zip(nifty_yf, nifty_raw):
        r = ind.evaluate_oracle_score(yf_sym, display=disp)
        if r: nifty_top5_res.append(r)

    return {"us100_top5": us100_top5_res, "nifty_top5": nifty_top5_res}

# ================================================================
# HEADER BAR
# ================================================================

col_title, col_menu = st.columns([6,1])

with col_title:
    st.markdown("### ⚡ QuantFX Terminal")

with col_menu:
    with st.popover("⚙️ Menu"):
        st.markdown("#### 📱 Telegram Alerts Setup")
        st.session_state.telegram_token = st.text_input("Bot token", st.session_state.telegram_token, type="password")
        st.session_state.telegram_chat_id = st.text_input("Chat ID", st.session_state.telegram_chat_id)

        if st.button("💾 Save"):
            save_telegram_config(st.session_state.telegram_token, st.session_state.telegram_chat_id)
            st.success("Saved!")

        if st.button("Send test"):
            ind.TELEGRAM_CONFIG["token"] = st.session_state.telegram_token
            ind.TELEGRAM_CONFIG["chat_id"] = st.session_state.telegram_chat_id
            ok, msg = ind.send_telegram_alert("✅ Test alert from QuantFX Terminal")
            st.success(msg) if ok else st.error(msg)

# ================================================================
# SIDEBAR
# ================================================================

symbol_options = {d:s for s,d in COMMODITIES+FOREX}
symbol_options.update({d:f"{t}.NS" for d,t in zip(ind.nifty200_raw, ind.nifty200_raw)})
symbol_options.update({d:ind.convert_us100_symbol(d) for d in ind.us100_raw})

custom_symbol = st.sidebar.text_input("Or type any Yahoo Finance ticker", "")
display_choice = st.sidebar.selectbox("Symbol", list(symbol_options.keys()))

current_symbol = custom_symbol.strip() if custom_symbol else symbol_options[display_choice]
current_display = custom_symbol.strip() if custom_symbol else display_choice

tf_choice = st.sidebar.selectbox("Timeframe", list(TIMEFRAMES.keys()))
current_interval, current_period = TIMEFRAMES[tf_choice]

ema_fast = st.sidebar.number_input("EMA Fast", 2, 50, 9)
ema_slow = st.sidebar.number_input("EMA Slow", 3, 100, 20)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎯 High-Conviction BUY Radar")

with st.sidebar:
    with st.spinner("Checking filters…"):
        top_signals = cached_filtered_top5_charts()

    if top_signals:
        for sig in top_signals[:5]:
            st.markdown(
                f"""
<div style="background-color:{COLOR_PANEL_BG};border:1px solid {COLOR_BULL};
padding:8px;border-radius:6px;margin-bottom:6px;">
<b style="color:{COLOR_BULL};">{sig['Ticker']} ({sig['Signal']})</b><br>
<span style="font-size:11px;color:{COLOR_TEXT_MUTED};">
Price: ${sig['Price']} | Score: {sig['Score']}<br>
TP1: {sig['TP1_PCT']}
</span>
</div>
""",
                unsafe_allow_html=True
            )
    else:
        st.info("No components match strict BUY criteria.")

tab_chart, tab_scanner = st.tabs(["📈 Chart", "🔎 Scanner"])

# ================================================================
# CHART TAB
# ================================================================

with tab_chart:
    with st.spinner(f"Loading {current_display}…"):
        df = cached_ohlc(current_symbol, current_period, current_interval)

    if df.empty:
        st.error("No data returned.")
    else:
        renko_df, brick_size = ind.build_atr_renko_df(df, 14, 2.0, ema_fast, ema_slow)

        if renko_df.empty:
            st.warning("Not enough movement for ATR Renko bricks.")
        else:
            ha_df = ind.compute_heikin_ashi(renko_df)
            ha_df["EMA_FAST"] = ha_df["Close"].ewm(span=ema_fast).mean()
            ha_df["EMA_SLOW"] = ha_df["Close"].ewm(span=ema_slow).mean()

            signals = ["HOLD"]
            for i in range(1,len(ha_df)):
                f_now, s_now = ha_df["EMA_FAST"].iloc[i], ha_df["EMA_SLOW"].iloc[i]
                f_prev, s_prev = ha_df["EMA_FAST"].iloc[i-1], ha_df["EMA_SLOW"].iloc[i-1]
                if f_now>s_now and f_prev<=s_prev: signals.append("BUY")
                elif f_now<s_now and f_prev>=s_prev: signals.append("SELL")
                else: signals.append("HOLD")
            ha_df["Signal"] = signals

            x = np.arange(len(renko_df))
            dates = pd.to_datetime(renko_df["Date"])
            hover_dates = dates.dt.strftime("%d %b %Y %H:%M")

            fig = make_subplots(
                rows=4, cols=1, shared_xaxes=True,
                row_heights=[0.28,0.32,0.2,0.2],
                vertical_spacing=0.02,
                subplot_titles=[
                    f"{current_display} — Heikin Ashi",
                    f"{current_display} — ATR Renko × 2 + EMA",
                    "MACD",
                    "RSI"
                ]
            )

            # Heikin Ashi
            fig.add_trace(go.Candlestick(
                x=x, open=ha_df["Open"], high=ha_df["High"],
                low=ha_df["Low"], close=ha_df["Close"],
                increasing_line_color=COLOR_BULL,
                decreasing_line_color=COLOR_BEAR,
                showlegend=False
            ), row=1,col=1)

            fig.add_trace(go.Scatter(x=x, y=ha_df["EMA_FAST"], line=dict(color=COLOR_MA9)), row=1,col=1)
            fig.add_trace(go.Scatter(x=x, y=ha_df["EMA_SLOW"], line=dict(color=COLOR_MA20)), row=1,col=1)

            # Renko
            fig.add_trace(go.Candlestick(
                x=x, open=renko_df["Open"], high=renko_df["High"],
                low=renko_df["Low"], close=renko_df["Close"],
                increasing_line_color=COLOR_BULL,
                decreasing_line_color=COLOR_BEAR,
                showlegend=False
            ), row=2,col=1)

            fig.add_trace(go.Scatter(x=x, y=renko_df["EMA_FAST"], line=dict(color=COLOR_MA9)), row=2,col=1)
            fig.add_trace(go.Scatter(x=x, y=renko_df["EMA_SLOW"], line=dict(color=COLOR_MA20)), row=2,col=1)

            # MACD
            fig.add_trace(go.Scatter(x=x, y=renko_df["MACD"], line=dict(color=COLOR_MACD_LINE)), row=3,col=1)
            fig.add_trace(go.Scatter(x=x, y=renko_df["MACD_Signal"], line=dict(color=COLOR_SIGNAL_LINE)), row=3,col=1)
            fig.add_hline(y=0, line_color=COLOR_ZERO_LINE, row=3,col=1)

            # RSI
            fig.add_trace(go.Scatter(x=x, y=renko_df["RSI"], line=dict(color="#FFD700")), row=4,col=1)
            fig.add_hline(y=70, line_color=COLOR_RED, row=4,col=1)
            fig.add_hline(y=30, line_color=COLOR_GREEN, row=4,col=1)
            fig.update_yaxes(range=[0,100], row=4,col=1)

            fig.update_layout(
                height=780,
                paper_bgcolor=COLOR_BG_DARK,
                plot_bgcolor=COLOR_BG_DARK,
                font=dict(color=COLOR_TEXT_MUTED),
                dragmode="pan"
            )

            col_chart, col_side = st.columns([2,1])

            with col_chart:
                st.plotly_chart(fig, use_container_width=True)

            with col_side:
                st.subheader("🗓️ 7-Day Outlook")
                outlook = cached_outlook(current_symbol, current_display, "1y", "1d")

                if not outlook:
                    st.info("Not enough history.")
                else:
                    dir_color = COLOR_GREEN if outlook["direction"]=="Bullish" else COLOR_RED
                    reasons_html = "".join(f"<li>{r}</li>" for r in outlook["reasons"])

                    st.markdown(
                        f"""
<div class="outlook-box">
<b style="color:{dir_color};">{outlook['direction']}</b><br>
Range: ${outlook['range_low']:,.2f} – ${outlook['range_high']:,.2f}<br>
Last: ${outlook['last_close']:,.2f}
<ul>{reasons_html}</ul>
</div>
""",
                        unsafe_allow_html=True
                    )

                st.subheader("📰 Latest Market News")
                news_items = cached_news(current_symbol)
                if news_items:
                    for item in news_items[:4]:
                        st.markdown(
                            f"""
<div class="news-card">
<a href="{item['link']}" target="_blank" style="color:{COLOR_BULL};font-size:11px;">
{item['title']}
</a><br>
<span style="font-size:9px;color:{COLOR_TEXT_MUTED};">Source: {item.get('publisher','Yahoo Finance')}</span>
</div>
""",
                            unsafe_allow_html=True
                        )
                else:
                    st.info("No recent news.")

# ================================================================
# SCANNER TAB
# ================================================================

with tab_scanner:
    st.subheader("⚡ Quick Top 5 Scan")

    if st.button("Run Top 5 Quick Scan"):
        st.session_state["top5_results"] = cached_top5_scan()

    top5 = st.session_state.get("top5_results")
    if top5:
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("### 🇺🇸 US100")
            df_us = pd.DataFrame(top5["us100_top5"])
            if not df_us.empty:
                st.dataframe(df_us, use_container_width=True)

        with c2:
            st.markdown("### 🇮🇳 Nifty200")
            df_nf = pd.DataFrame(top5["nifty_top5"])
            if not df_nf.empty:
                st.dataframe(df_nf, use_container_width=True)

    st.markdown("---")
    st.subheader("🌐 Full Universe Scanner")

    include_wide = st.checkbox("Include full Nifty200 + US100 universe")
    if st.button("Run full scan"):
        st.session_state["scan_results"] = cached_scan(include_wide)

    results = st.session_state.get("scan_results")
    if results:
        all_rows = results["commodities"] + results["forex"] + results["nifty200"] + results["us100"]
        df_scan = pd.DataFrame(all_rows)

        search = st.text_input
