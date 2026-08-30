"""
QuantFX Terminal — Web Edition
Streamlit + Plotly rewrite of the PyQt6 desktop terminal. All indicator
math lives in indicators.py (unchanged logic: ATR Renko, Heikin Ashi,
EMA cross, MACD, RSI, 7-day outlook). This file is UI only.

Run locally:    streamlit run app.py
Then open the "Network URL" it prints on your phone's Chrome (same Wi-Fi),
or deploy it (see README.md) to get a public link you can open anywhere.
"""
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
# PERSISTENT TELEGRAM CONFIG (saved to a local JSON file next to app.py,
# so it survives closing the browser tab / restarting the app)
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
COMMODITIES = [("GC=F", "GOLD"), ("SI=F", "SILVER"), ("KC=F", "COFFEE"), ("CL=F", "CRUDE"), ("NG=F", "GAS")]
FOREX = [("EURUSD=X", "EUR/USD"), ("GBPUSD=X", "GBP/USD"), ("USDJPY=X", "USD/JPY"),
         ("AUDUSD=X", "AUD/USD"), ("USDCAD=X", "USD/CAD")]

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
# CACHED DATA FETCHERS & STRICT FILTER LOGIC
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
    """Evaluates top components and strictly enforces BUY signal, Score >= 50%, and TP1% >= 5%."""
    qualified = []
    
    us_yf = getattr(ind, "us100_yf", ["AAPL", "MSFT", "NVDA", "AMZN", "META"])[:5]
    us_raw = getattr(ind, "us100_raw", ["AAPL", "MSFT", "NVDA", "AMZN", "META"])[:5]
    nifty_yf = getattr(ind, "nifty200_yf", ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"])[:5]
    nifty_raw = getattr(ind, "nifty200_raw", ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"])[:5]
    
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
    return {"commodities": comm_res, "forex": forex_res, "nifty200": nifty_res, "us100": us100_res}


@st.cache_data(ttl=300, show_spinner=False)
def cached_top5_scan():a
    """Dedicated fast scan for Top 5 US100 & Top 5 Nifty200 components."""
    us100_top5_res, nifty_top5_res = [], []
    
    us_yf_top5 = getattr(ind, "us100_yf", ["AAPL", "MSFT", "NVDA", "AMZN", "META"])[:5]
    us_raw_top5 = getattr(ind, "us100_raw", ["AAPL", "MSFT", "NVDA", "AMZN", "META"])[:5]
    
    nifty_yf_top5 = getattr(ind, "nifty200_yf", ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"])[:5]
    nifty_raw_top5 = getattr(ind, "nifty200_raw", ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"])[:5]

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
# TOP HEADER BAR — Embedding Telegram Config inside the Menu (3 dots)
# =====================================================================
col_title, col_menu = st.columns([6, 1])

with col_title:
    st.markdown("### ⚡ QuantFX Terminal")

with col_menu:
    with st.popover("⚙️ Menu"):
        st.markdown("#### 📱 Telegram Alerts Setup")
        st.session_state.telegram_token = st.text_input("Bot token", value=st.session_state.telegram_token, type="password")
        st.session_state.telegram_chat_id = st.text_input("Chat ID", value=st.session_state.telegram_chat_id)

        col_save, col_test = st.columns(2)
        with col_save:
            if st.button("💾 Save"):
                save_telegram_config(st.session_state.telegram_token, st.session_state.telegram_chat_id)
                st.success("Saved!")
        with col_test:
            if st.button("Send test"):
                ind.TELEGRAM_CONFIG["token"] = st.session_state.telegram_token
                ind.TELEGRAM_CONFIG["chat_id"] = st.session_state.telegram_chat_id
                ok, msg = ind.send_telegram_alert(f"✅ Test alert from QuantFX Terminal")
                st.success(msg) if ok else st.error(msg)

        if TELEGRAM_CONFIG_FILE.exists():
            st.caption("🔒 Config loaded from server.")
        else:
            st.caption("Not saved yet.")

# =====================================================================
# SIDEBAR — symbol / timeframe / EMA / High-Conviction Radar
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
        for sig in top_signals[:5]:  # Expanded display count for more room!
            st.sidebar.markdown(
                f"""
                <div style="background-color: {COLOR_PANEL_BG}; border: 1px solid {COLOR_BULL}; border-radius: 6px; padding: 8px; margin-bottom: 6px;">
                    <span style="color: {COLOR_BULL}; font-weight: bold; font-size: 13px;">{sig['Ticker']} ({sig['Signal']})</span><br>
                    <span style="font-size: 11px; color: {COLOR_TEXT_MUTED};">
                        Price: ${sig['Price']} | Score: <b>{sig['Score']}</b><br>
                        Target 1 (TP1): <b>{sig['TP1_PCT']}</b>
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
# CHART TAB (Two-Column Layout: Left = Chart, Right = Outlook & News)
# =====================================================================
with tab_chart:
    with st.spinner(f"Loading {current_display}…"):
        df = cached_ohlc(current_symbol, current_period, current_interval)

    if df.empty:
        st.error(f"No data returned for {current_display}. Check the ticker symbol.")
    else:
        renko_df, brick_size = ind.build_atr_renko_df(
            df, atr_period=14, atr_multiplier=2.0, ema_fast=ema_fast, ema_slow=ema_slow
        )

        if renko_df.empty:
            st.warning(f"Not enough price movement yet to form ATR Renko bricks for {current_display}.")
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
                            bgcolor="#004D1A", bordercolor="#00FF9A", borderwidth=1, borderpad=3,
                            row=row, col=1,
                        )
                    elif s == "SELL":
                        fig.add_annotation(
                            x=xi, y=yi, text=f"<b>{sell_text}</b>", showarrow=False,
                            font=dict(color="#FFFFFF", size=9),
                            bgcolor="#4D004D", bordercolor="#FF66CC", borderwidth=1, borderpad=3,
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

            # --- Row 1: Heikin Ashi ---
            fig.add_trace(go.Candlestick(
                x=x, open=ha_df["Open"], high=ha_df["High"], low=ha_df["Low"], close=ha_df["Close"],
                increasing_line_color=COLOR_BULL, decreasing_line_color=COLOR_BEAR,
                increasing_fillcolor=COLOR_BULL, decreasing_fillcolor=COLOR_BEAR,
                text=hover_dates, name="Heikin Ashi", showlegend=False,
            ), row=1, col=1)
            fig.add_trace(go.Scatter(x=x, y=ha_df["EMA_FAST"], line=dict(color=COLOR_MA9, width=1.5),
                                     name=f"EMA {ema_fast}"), row=1, col=1)
            fig.add_trace(go.Scatter(x=x, y=ha_df["EMA_SLOW"], line=dict(color=COLOR_MA20, width=1.5),
                                     name=f"EMA {ema_slow}"), row=1, col=1)
            ha_buys = ha_df[ha_df["Signal"] == "BUY"]
            ha_sells = ha_df[ha_df["Signal"] == "SELL"]
            add_signal_labels(
                fig,
                list(x[ha_buys.index]) + list(x[ha_sells.index]),
                list(ha_buys["Low"] - brick_size * 0.4) + list(ha_sells["High"] + brick_size * 0.4),
                ["BUY"] * len(ha_buys) + ["SELL"] * len(ha_sells),
                row=1,
            )

            # --- Row 2: ATR Renko + EMA cross ---
            fig.add_trace(go.Candlestick(
                x=x, open=renko_df["Open"], high=renko_df["High"], low=renko_df["Low"], close=renko_df["Close"],
                increasing_line_color=COLOR_BULL, decreasing_line_color=COLOR_BEAR,
                increasing_fillcolor=COLOR_BULL, decreasing_fillcolor=COLOR_BEAR,
                text=hover_dates, name="Renko", showlegend=False,
            ), row=2, col=1)
            fig.add_trace(go.Scatter(x=x, y=renko_df["EMA_FAST"], line=dict(color=COLOR_MA9, width=1.5),
                                     name=f"EMA {ema_fast} (Renko)", showlegend=False), row=2, col=1)
            fig.add_trace(go.Scatter(x=x, y=renko_df["EMA_SLOW"], line=dict(color=COLOR_MA20, width=1.5),
                                     name=f"EMA {ema_slow} (Renko)", showlegend=False), row=2, col=1)
            r_buys = renko_df[renko_df["Signal"] == "BUY"]
            r_sells = renko_df[renko_df["Signal"] == "SELL"]
            add_signal_labels(
                fig,
                list(x[r_buys.index]) + list(x[r_sells.index]),
                list(r_buys["Close"] - brick_size * 0.4) + list(r_sells["Close"] + brick_size * 0.4),
                ["BUY"] * len(r_buys) + ["SELL"] * len(r_sells),
                row=2,
            )

            # --- Row 3: MACD ---
            fig.add_trace(go.Scatter(x=x, y=renko_df["MACD"], line=dict(color=COLOR_MACD_LINE, width=1.3),
                                     name="MACD"), row=3, col=1)
            fig.add_trace(go.Scatter(x=x, y=renko_df["MACD_Signal"], line=dict(color=COLOR_SIGNAL_LINE, width=1.3),
                                     name="Signal"), row=3, col=1)
            fig.add_hline(y=0, line_color=COLOR_ZERO_LINE, line_width=0.8, row=3, col=1)
            div_buys = renko_df[renko_df["Div_Signal"] == "BUY"]
            div_sells = renko_df[renko_df["Div_Signal"] == "SELL"]
            add_signal_labels(
                fig,
                list(x[div_buys.index]) + list(x[div_sells.index]),
                list(div_buys["MACD"] - abs(renko_df["MACD"]).max() * 0.05) + list(div_sells["MACD"] + abs(renko_df["MACD"]).max() * 0.05),
                ["BUY"] * len(div_buys) + ["SELL"] * len(div_sells),
                row=3,
            )

            # --- Row 4: RSI ---
            fig.add_trace(go.Scatter(x=x, y=renko_df["RSI"], line=dict(color="#FFD700", width=1.3),
                                     name="RSI"), row=4, col=1)
            fig.add_hline(y=70, line_color=COLOR_RED, line_width=0.8, line_dash="dash", row=4, col=1)
            fig.add_hline(y=30, line_color=COLOR_GREEN, line_width=0.8, line_dash="dash", row=4, col=1)
            fig.update_yaxes(range=[0, 100], row=4, col=1)

            step = max(len(x) // 8, 1)
            fig.update_xaxes(
                tickmode="array",
                tickvals=list(x[::step]),
                ticktext=[d.strftime("%d-%m") for d in dates[::step]],
                row=4, col=1,
            )
            for r in range(1, 5):
                fig.update_xaxes(rangeslider_visible=False, row=r, col=1)
                fig.update_yaxes(side="right", row=r, col=1)

            fig.update_layout(
                height=780,
                paper_bgcolor=COLOR_BG_DARK,
                plot_bgcolor=COLOR_BG_DARK,
                font=dict(color=COLOR_TEXT_MUTED, size=11),
                margin=dict(l=10, r=10, t=30, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0),
                dragmode="pan",
            )

        # --- Side-by-Side Layout: Left (Chart), Right (7-Day Outlook & News) ---
        col_chart, col_side = st.columns([2, 1])

        with col_chart:
            if not renko_df.empty:
                st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displaylogo": False})

        with col_side:
            st.subheader("🗓️ 7-Day Outlook")
            with st.spinner("Computing outlook…"):
                outlook = cached_outlook(current_symbol, current_display, "1y", "1d")

            if not outlook:
                st.info(f"Not enough daily history to project {current_display}.")
            else:
                bias_score = outlook["bias_score"]
                conditions_met = abs(bias_score) >= 2.0
                dir_color = {"Bullish": COLOR_GREEN, "Bearish": COLOR_RED}.get(outlook["direction"], COLOR_TEXT_MUTED)
                badge = "🟢 CONDITIONS MET" if conditions_met else "🔴 CONDITIONS NOT MET"
                reasons_html = "".join(f"<li>{r}</li>" for r in outlook["reasons"])
                st.markdown(
                    f"""
                    <div class="outlook-box">
                        <span style="font-weight:bold;color:{dir_color};font-size:14px;">{outlook['direction']}</span>
                        &nbsp;&nbsp;<b>{badge}</b><br>
                        <span style="color:{COLOR_TEXT_MUTED}; font-size: 11px;">
                            Range: ${outlook['range_low']:,.2f} – ${outlook['range_high']:,.2f} (Last: ${outlook['last_close']:,.2f})
                        </span>
                        <ul style="margin-top:6px; margin-bottom: 4px; padding-left: 15px; font-size: 11px;">{reasons_html}</ul>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.subheader("📰 Latest Market News")
            news_items = cached_news(current_symbol)
            if news_items:
                for item in news_items[:4]:
                    title = item.get("title", "No title")
                    publisher = item.get("publisher", "Yahoo Finance")
                    link = item.get("link", "#")
                    st.markdown(
                        f"""
                        <div class="news-card">
                            <a href="{link}" target="_blank" style="color: {COLOR_BULL}; text-decoration: none; font-size: 11px; font-weight: bold;">{title}</a><br>
                            <span style="color: {COLOR_TEXT_MUTED}; font-size: 9px;">Source: {publisher}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.info("No recent news articles found for this ticker.")

# =====================================================================
# SCANNER TAB
# =====================================================================
with tab_scanner:
    st.subheader("⚡ Quick Top 5 US100 & Top 5 Nifty200 Scan")
    st.caption("Instantly evaluate the top 5 heavyweights of US100 and Nifty200 without waiting for the full universe scan.")
    
    if st.button("Run Top 5 Quick Scan", type="primary"):
        with st.spinner("Scanning top index components..."):
            top5_results = cached_top5_scan()
            st.session_state["top5_results"] = top5_results

    top5_data = st.session_state.get("top5_results")
    if top5_data:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🇺🇸 US100 (Top 5)")
            us_top5_df = pd.DataFrame(top5_data["us100_top5"])
            if not us_top5_df.empty:
                st.dataframe(us_top5_df[["Ticker", "Price", "ChangePct", "Signal", "Score", "SL", "TP1"]], use_container_width=True)
            else:
                st.info("No data returned for US100 top 5.")
        with c2:
            st.markdown("### 🇮🇳 Nifty200 (Top 5)")
            nifty_top5_df = pd.DataFrame(top5_data["nifty_top5"])
            if not nifty_top5_df.empty:
                st.dataframe(nifty_top5_df[["Ticker", "Price", "ChangePct", "Signal", "Score", "SL", "TP1"]], use_container_width=True)
            else:
                st.info("No data returned for Nifty200 top 5.")

    st.markdown("---")
    st.subheader("🌐 Full Universe Scanner")
    st.caption("Commodities + forex always included. Full Nifty200 + US100 universe is slower (200+ symbols).")
    include_wide = st.checkbox("Include full Nifty200 + US100 universe (slower)", value=False)
    run_full = st.button("Run full market scan")

    if run_full:
        with st.spinner("Scanning full markets…"):
            results = cached_scan(include_wide)
        st.session_state["scan_results"] = results

    results = st.session_state.get("scan_results")
    if results:
        all_rows = results["commodities"] + results["forex"] + results["nifty200"] + results["us100"]
        if all_rows:
            df_scan = pd.DataFrame(all_rows)
            search = st.text_input("Filter by ticker")
            if search:
                df_scan = df_scan[df_scan["Ticker"].str.contains(search, case=False, na=False)]
            st.dataframe(
                df_scan[["Ticker", "Price", "ChangePct", "Signal", "Score", "SL", "TP1", "TP1_PCT", "TP2"]],
                use_container_width=True, height=500,
            )

            if st.button("Send filtered BUY alerts to Telegram"):
                ind.TELEGRAM_CONFIG["token"] = st.session_state.telegram_token
                ind.TELEGRAM_CONFIG["chat_id"] = st.session_state.telegram_chat_id
                valid_buys = []
                for row in all_rows:
                    try:
                        score = float(str(row["Score"]).replace("%", ""))
                        tp1_pct = float(str(row["TP1_PCT"]).replace("%", ""))
                        signal = str(row["Signal"]).upper()
                        
                        if signal == "BUY" and score >= 50.0 and tp1_pct >= 5.0:
                            valid_buys.append(row)
                    except (ValueError, KeyError):
                        continue
                if not valid_buys:
                    st.info("No symbols currently meet the strict criteria (BUY signal, Score ≥ 50%, TP1% ≥ 5%).")
                else:
                    lines = ["*🚨 High-Conviction BUY Alerts* _(Score ≥ 50%, TP1% ≥ 5%)_"]
                    for r in valid_buys[:15]:
                        lines.append(f"• *{r['Ticker']}*: {r['Signal']} | Price: {r['Price']} | Score: {r['Score']} | TP1: {r['TP1_PCT']}")
                    ok, msg = ind.send_telegram_alert("\n".join(lines))
                    st.success(f"Sent {len(valid_buys)} verified BUY alerts.") if ok else st.error(msg)
        else:
            st.info("No results — try running the scanner again.")
# =====================================================================
# BACKGROUND CRON TRIGGER
# =====================================================================
# This intercepts incoming cron requests to execute the scan engine
if "trigger" in st.query_params and st.query_params["trigger"] == "hourly_scan":
    import run_scan
    try:
        run_scan.main()
        st.success("Background scan completed successfully!")
    except Exception as e:
        st.error(f"Scan execution error: {str(e)}")
    st.stop() # Stops execution here so it doesn't render the whole UI for the cron bot
