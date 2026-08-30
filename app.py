import json
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import indicators as ind

# =====================================================================
# PERSISTENT TELEGRAM CONFIG
# =====================================================================

TELEGRAM_CONFIG_FILE = Path(__file__).parent / "telegram_config.json"

def load_saved_telegram_config():
    try:
        data = json.loads(TELEGRAM_CONFIG_FILE.read_text())
        return data.get("token", ""), data.get("chat_id", "")
    except (FileNotFoundError, json.JSONDecodeError):
        return "", ""

def save_telegram_config(token, chat_id):
    TELEGRAM_CONFIG_FILE.write_text(json.dumps({"token": token, "chat_id": chat_id}))

# =====================================================================
# THEME
# =====================================================================

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

st.set_page_config(page_title="QuantFX Terminal", layout="wide", initial_sidebar_state="expanded")

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
.quick-scan-box {{
    background-color: {COLOR_PANEL_BG};
    border: 1px solid #1f293d;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
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

# =====================================================================
# SYMBOL UNIVERSE
# =====================================================================

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

if "telegram_token" not in st.session_state:
    saved_token, saved_chat_id = load_saved_telegram_config()
    st.session_state.telegram_token = saved_token
    st.session_state.telegram_chat_id = saved_chat_id

# =====================================================================
# CACHED DATA FETCHERS
# =====================================================================

@st.cache_data(ttl=60, show_spinner=False)
def cached_ohlc(symbol, period, interval):
    return ind.fetch_live_ohlc(symbol, period=period, interval=interval)

@st.cache_data(ttl=60, show_spinner=False)
def cached_outlook(symbol, display, period, interval):
    return ind.compute_7day_outlook(symbol, display, period=period, interval=interval)

@st.cache_data(ttl=300, show_spinner=False)
def cached_news(symbol):
    try:
        t = yf.Ticker(symbol)
        return t.news if hasattr(t, "news") else []
    except Exception:
        return []

@st.cache_data(ttl=300, show_spinner=False)
def cached_filtered_top5_charts():
    """Strict BUY filter: BUY + Score ≥ 50% + TP1% ≥ 5%."""
    qualified = []

    us_yf = getattr(ind, "us100_yf", ["AAPL", "MSFT", "NVDA", "AMZN", "META"])[:5]
    us_raw = getattr(ind, "us100_raw", ["AAPL", "MSFT", "NVDA", "AMZN", "META"])[:5]

    nifty_yf = getattr(ind, "nifty200_yf",
                       ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"])[:5]
    nifty_raw = getattr(ind, "nifty200_raw",
                        ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"])[:5]

    universe = list(zip(us_yf, us_raw)) + list(zip(nifty_yf, nifty_raw))

    for yf_sym, disp in universe:
        r = ind.evaluate_oracle_score(yf_sym, display=disp)
        if r:
            try:
                score = float(str(r.get("Score", "0")).replace("%", ""))
                tp1_pct = float(str(r.get("TP1_PCT", "0")).replace("%", ""))
                signal = str(r.get("Signal", "")).upper()

                if signal == "BUY" and score >= 50.0 and tp1_pct >= 5.0:
                    qualified.append(r)
            except (ValueError, TypeError):
                continue

    return qualified

@st.cache_data(ttl=300, show_spinner=False)
def cached_scan(include_wide_universe):
    comm_res, forex_res, nifty_res, us100_res = [], [], [], []

    for s, d in COMMODITIES:
        r = ind.evaluate_oracle_score(s, display=d)
        if r:
            comm_res.append(r)

    for s, d in FOREX:
        r = ind.evaluate_oracle_score(s, display=d)
        if r:
            forex_res.append(r)

    if include_wide_universe:
        for yf_sym, disp in zip(ind.nifty200_yf, ind.nifty200_raw):
            r = ind.evaluate_oracle_score(yf_sym, display=disp)
            if r:
                nifty_res.append(r)

        for yf_sym, disp in zip(ind.us100_yf, ind.us100_raw + ["IXIC"]):
            r = ind.evaluate_oracle_score(yf_sym, display=disp)
            if r:
                us100_res.append(r)

    return {
        "commodities": comm_res,
        "forex": forex_res,
        "nifty200": nifty_res,
        "us100": us100_res
    }

@st.cache_data(ttl=300, show_spinner=False)
def cached_top5_scan():
    """Dedicated fast scan for Top 5 US100 & Top 5 Nifty200 components."""
    us100_top5_res, nifty_top5_res = [], []

    us_yf_top5 = getattr(ind, "us100_yf", ["AAPL", "MSFT", "NVDA", "AMZN", "META"])[:5]
    us_raw_top5 = getattr(ind, "us100_raw", ["AAPL", "MSFT", "NVDA", "AMZN", "META"])[:5]

    nifty_yf_top5 = getattr(ind, "nifty200_yf",
                            ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"])[:5]
    nifty_raw_top5 = getattr(ind, "nifty200_raw",
                             ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"])[:5]

    for yf_sym, disp in zip(us_yf_top5, us_raw_top5):
        r = ind.evaluate_oracle_score(yf_sym, display=disp)
        if r:
            us100_top5_res.append(r)

    for yf_sym, disp in zip(nifty_yf_top5, nifty_raw_top5):
        r = ind.evaluate_oracle_score(yf_sym, display=disp)
        if r:
            nifty_top5_res.append(r)

    return {"us100_top5": us100_top5_res, "nifty_top5": nifty_top5_res}

# =====================================================================
# HEADER BAR
# =====================================================================

col_title, col_menu = st.columns([6, 1])

with col_title:
    st.markdown("### ⚡ QuantFX Terminal")

with col_menu:
    with st.popover("⚙️ Menu"):
        st.markdown("#### 📱 Telegram Alerts Setup")

        st.session_state.telegram_token = st.text_input(
            "Bot token", value=st.session_state.telegram_token, type="password"
        )
        st.session_state.telegram_chat_id = st.text_input(
            "Chat ID", value=st.session_state.telegram_chat_id
        )

        col_save, col_test = st.columns(2)

        with col_save:
            if st.button("💾 Save"):
                save_telegram_config(
                    st.session_state.telegram_token,
                    st.session_state.telegram_chat_id
                )
                st.success("Saved!")

        with col_test:
            if st.button("Send test"):
                ind.TELEGRAM_CONFIG["token"] = st.session_state.telegram_token
                ind.TELEGRAM_CONFIG["chat_id"] = st.session_state.telegram_chat_id
                ok, msg = ind.send_telegram_alert("✅ Test alert from QuantFX Terminal")
                st.success(msg) if ok else st.error(msg)

        if TELEGRAM_CONFIG_FILE.exists():
            st.caption("🔒 Config loaded from server.")
        else:
            st.caption("Not saved yet.")

# =====================================================================
# SIDEBAR
# =====================================================================

symbol_options = {d: s for s, d in COMMODITIES + FOREX}
symbol_options.update({d: f"{t}.NS" for d, t in zip(ind.nifty200_raw, ind.nifty200_raw)})
symbol_options.update({d: ind.convert_us100_symbol(d) for d in ind.us100_raw})

custom_symbol = st.sidebar.text_input("Or type any Yahoo Finance ticker", "")
display_choice = st.sidebar.selectbox("Symbol", list(symbol_options.keys()), index=0)

if custom_symbol.strip():
    current_symbol = custom_symbol.strip()
    current_display = custom_symbol.strip()
else:
    current_symbol = symbol_options[display_choice]
    current_display = display_choice

tf_choice = st.sidebar.selectbox("Timeframe", list(TIMEFRAMES.keys()), index=3)
current_interval, current_period = TIMEFRAMES[tf_choice]

ema_fast = st.sidebar.number_input("EMA Fast", min_value=2, max_value=50, value=9)
ema_slow = st.sidebar.number_input("EMA Slow", min_value=3, max_value=100, value=20)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎯 High-Conviction BUY Radar")
st.sidebar.caption("BUY | Score ≥ 50% & TP1% ≥ 5%")

with st.sidebar.container():
    with st.spinner("Checking high-conviction filters..."):
        top_signals = cached_filtered_top5_charts()

        if top_signals:
            for sig in top_signals[:5]:
                st.sidebar.markdown(
                    f"""
<div style="background-color:{COLOR_PANEL_BG};border:1px solid {COLOR_BULL};
border-radius:6px;padding:8px;margin-bottom:6px;">
<span style="color:{COLOR_BULL};font-weight:bold;font-size:13px;">
{sig['Ticker']} ({sig['Signal']})
</span><br>
<span style="font-size:11px;color:{COLOR_TEXT_MUTED};">
Price: ${sig['Price']} | Score: <b>{sig['Score']}</b><br>
TP1: <b>{sig['TP1_PCT']}</b>
</span>
</div>
""",
                    unsafe_allow_html=True
                )
        else:
            st.sidebar.info("No components currently match strict BUY criteria.")

st.sidebar.caption("Tip: on your phone, add app to Home Screen.")

tab_chart, tab_scanner = st.tabs(["📈 Chart", "🔎 Scanner"])

# =====================================================================
# CHART TAB
# =====================================================================

with tab_chart:
    with st.spinner(f"Loading {current_display}…"):
        df = cached_ohlc(current_symbol, current_period, current_interval)

        if df.empty:
            st.error(f"No data returned for {current_display}. Check the ticker symbol.")
        else:
            renko_df, brick_size = ind.build_atr_renko_df(
                df, atr_period=14, atr_multiplier=2.0,
                ema_fast=ema_fast, ema_slow=ema_slow
            )

            if renko_df.empty:
                st.warning(
                    f"Not enough price movement yet to form ATR Renko bricks for {current_display}."
                )
            else:
                ha_df = ind.compute_heikin_ashi(renko_df)
                ha_df["EMA_FAST"] = ha_df["Close"].ewm(span=ema_fast, adjust=False).mean()
                ha_df["EMA_SLOW"] = ha_df["Close"].ewm(span=ema_slow, adjust=False).mean()

                ha_signals = ["HOLD"]
                for i in range(1, len(ha_df)):
                    f_now, s_now = ha_df["EMA_FAST"].iloc[i], ha_df["EMA_SLOW"].iloc[i]
                    f_prev, s_prev = ha_df["EMA_FAST"].iloc[i - 1], ha_df["EMA_SLOW"].iloc[i - 1]

                    if f_now > s_now and f_prev <= s_prev:
                        ha_signals.append("BUY")
                    elif f_now < s_now and f_prev >= s_prev:
                        ha_signals.append("SELL")
                    else:
                        ha_signals.append("HOLD")

                ha_df["Signal"] = ha_signals

                x = np.arange(len(renko_df))
                dates = pd.to_datetime(renko_df["Date"])
                hover_dates = dates.dt.strftime("%d %b %Y %H:%M")

                def add_signal_labels(fig, xs, ys, sig, row, buy_text="BUY", sell_text="SELL"):
                    for xi, yi, s in zip(xs, ys, sig):
                        if s == "BUY":
                            fig.add_annotation(
                                x=xi, y=yi, text=f"<b>{buy_text}</b>", showarrow=False,
                                font=dict(color="#FFFFFF", size=9),
                                bgcolor="#004D1A", bordercolor="#00FF9A",
                                borderwidth=1, borderpad=3,
                                row=row, col=1,
                            )
                        elif s == "SELL":
                            fig.add_annotation(
                                x=xi, y=yi, text=f"<b>{sell_text}</b>", showarrow=False,
                                font=dict(color="#FFFFFF", size=9),
                                bgcolor="#4D004D", bordercolor="#FF66CC",
                                borderwidth=1, borderpad=3,
                                row=row, col=1,
                            )

                fig = make_subplots(
                    rows=4, cols=1, shared_xaxes=True,
                    row_heights=[0.28, 0.32, 0.2, 0.2],
                    vertical_spacing=0.02,
                    subplot_titles=(
                        f"{current_display} — Heikin Ashi",
                        f"{current_display} — ATR Renko × 2 + EMA Cross",
                        "MACD Cross Strategy",
                        "RSI",
                    ),
                )

                # Row 1: Heikin Ashi
                fig.add_trace(go.Candlestick(
                    x=x, open=ha_df["Open"], high=ha_df["High"],
                    low=ha_df["Low"], close=ha_df["Close"],
                    increasing_line_color=COLOR_BULL,
                    decreasing_line_color=COLOR_BEAR,
                    increasing_fillcolor=COLOR_BULL,
                    decreasing_fillcolor=COLOR_BEAR,
                    text=hover_dates, name="Heikin Ashi", showlegend=False,
                ), row=1, col=1)

                fig.add_trace(go.Scatter(
                    x=x, y=ha_df["EMA_FAST"],
                    line=dict(color=COLOR_MA9, width=1.5),
                    name=f"EMA {ema_fast}"
                ), row=1, col=1)

                fig.add_trace(go.Scatter(
                    x=x, y=ha_df["EMA_SLOW"],
                    line=dict(color=COLOR_MA20, width=1.5),
                    name=f"EMA {ema_slow}"
                ), row=1, col=1)

                ha_buys = ha_df[ha_df["Signal"] == "BUY"]
                ha_sells = ha_df[ha_df["Signal"] == "SELL"]

                add_signal_labels(
                    fig,
                    list(x[ha_buys.index]) + list(x[ha_sells.index]),
                    list(ha_buys["Low"] - brick_size * 0.4) +
                    list(ha_sells["High"] + brick_size * 0.4),
                    ["BUY"] * len(ha_buys) + ["SELL"] * len(ha_sells),
                    row=1,
                )

                # Row 2: ATR Renko + EMA
                fig.add_trace(go.Candlestick(
                    x=x, open=renko_df["Open"], high=renko_df["High"],
                    low=renko_df["Low"], close=renko_df["Close"],
                    increasing_line_color=COLOR_BULL,
                    decreasing_line_color=COLOR_BEAR,
                    increasing_fillcolor=COLOR_BULL,
                    decreasing_fillcolor=COLOR_BEAR,
                    text=hover_dates, name="Renko", showlegend=False,
                ), row=2, col=1)

                fig.add_trace
