import numpy as np
import pandas as pd
import yfinance as yf
import requests
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os

# =====================================================================
# PAGE CONFIG
# =====================================================================

st.set_page_config(
    page_title="QuantFX Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =====================================================================
# COLORS – TradingView-style dark + neon
# =====================================================================

COLOR_BG_DARK = "#0B0E11"
COLOR_PANEL_BG = "#11151C"
COLOR_BORDER = "#202635"
COLOR_TEXT_MAIN = "#E5E9F0"
COLOR_TEXT_MUTED = "#9FA8C3"

COLOR_BULL = "#26FF9A"
COLOR_BEAR = "#FF4F7B"

COLOR_GREEN = "#00FF66"
COLOR_RED = "#FF3333"

COLOR_MA_FAST = "#00FF66"   # EMA 9
COLOR_MA_SLOW = "#FF3333"   # EMA 20

COLOR_MACD_LINE = "#2962FF"
COLOR_SIGNAL_LINE = "#FF6D00"
COLOR_ZERO_LINE = "#4C566A"

COLOR_BOS_DEMAND = "#26FF9A"
COLOR_BOS_SUPPLY = "#FF4F7B"
COLOR_CHOCH_DEMAND = "#00D4FF"
COLOR_CHOCH_SUPPLY = "#FF9900"

COLOR_PB_BUY = "#00FFAA"
COLOR_PB_SELL = "#FF2255"

# =====================================================================
# GLOBAL DARK THEME CSS & BLINKING ANIMATION
# =====================================================================

st.markdown(
    f"""
<style>
.stApp {{ background-color: {COLOR_BG_DARK}; }}
section[data-testid="stSidebar"] {{ background-color: {COLOR_PANEL_BG}; }}

div[data-testid="stMetric"] {{
    background-color: {COLOR_PANEL_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 10px 14px;
}}

.qfx-badge {{
    display:inline-block; padding:3px 10px; border-radius:4px;
    font-weight:700; font-size:10px; letter-spacing:0.5px;
}}

.js-plotly-plot .plotly .gtitle,
.js-plotly-plot .plotly .xtitle,
.js-plotly-plot .plotly .ytitle,
.js-plotly-plot .plotly .legendtext,
.js-plotly-plot .plotly .xtick text,
.js-plotly-plot .plotly .ytick text,
.js-plotly-plot .plotly .annotation text {{
    font-size: 10px !important;
}}

@keyframes signalBlink {{
    0% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.15; transform: scale(1.18); }}
    100% {{ opacity: 1; transform: scale(1); }}
}}

.js-plotly-plot svg path[fill="{COLOR_PB_BUY}"],
.js-plotly-plot svg path[stroke="{COLOR_PB_BUY}"],
.js-plotly-plot svg text[fill="{COLOR_PB_BUY}"],
.js-plotly-plot svg path[fill="{COLOR_PB_SELL}"],
.js-plotly-plot svg path[stroke="{COLOR_PB_SELL}"],
.js-plotly-plot svg text[fill="{COLOR_PB_SELL}"] {{
    animation: signalBlink 1.1s infinite ease-in-out;
    transform-origin: center;
}}
</style>
""",
    unsafe_allow_html=True,
)

# =====================================================================
# TELEGRAM CONFIG
# =====================================================================

TG_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".qfx_telegram_config.json")

def load_telegram_config():
    try:
        if os.path.exists(TG_CONFIG_PATH):
            with open(TG_CONFIG_PATH, "r") as f:
                data = json.load(f)
            return data.get("tg_token", ""), data.get("tg_chat", "")
    except Exception:
        pass
    return "", ""

def save_telegram_config(token, chat_id):
    try:
        with open(TG_CONFIG_PATH, "w") as f:
            json.dump({"tg_token": token, "tg_chat": chat_id}, f)
        return True, "Saved."
    except Exception as e:
        return False, str(e)

def send_telegram_alert(message, token, chat_id):
    token = (token or "").strip()
    chat_id = (chat_id or "").strip()

    if not token or not chat_id:
        return False, "Bot Token or Chat ID is missing."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}

    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        if data.get("ok"):
            return True, "Success"
        return False, data.get("description", "Unknown Telegram API error")
    except Exception as e:
        return False, str(e)
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os

# =====================================================================
# PAGE CONFIG
# =====================================================================

st.set_page_config(
    page_title="QuantFX Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =====================================================================
# COLORS – TradingView-style dark + neon
# =====================================================================

COLOR_BG_DARK = "#0B0E11"
COLOR_PANEL_BG = "#11151C"
COLOR_BORDER = "#202635"
COLOR_TEXT_MAIN = "#E5E9F0"
COLOR_TEXT_MUTED = "#9FA8C3"

COLOR_BULL = "#26FF9A"
COLOR_BEAR = "#FF4F7B"

COLOR_GREEN = "#00FF66"
COLOR_RED = "#FF3333"

COLOR_MA_FAST = "#00FF66"   # EMA 9
COLOR_MA_SLOW = "#FF3333"   # EMA 20

COLOR_MACD_LINE = "#2962FF"
COLOR_SIGNAL_LINE = "#FF6D00"
COLOR_ZERO_LINE = "#4C566A"

COLOR_BOS_DEMAND = "#26FF9A"
COLOR_BOS_SUPPLY = "#FF4F7B"
COLOR_CHOCH_DEMAND = "#00D4FF"
COLOR_CHOCH_SUPPLY = "#FF9900"

COLOR_PB_BUY = "#00FFAA"
COLOR_PB_SELL = "#FF2255"

# =====================================================================
# GLOBAL DARK THEME CSS & BLINKING ANIMATION
# =====================================================================

st.markdown(
    f"""
<style>
.stApp {{ background-color: {COLOR_BG_DARK}; }}
section[data-testid="stSidebar"] {{ background-color: {COLOR_PANEL_BG}; }}

div[data-testid="stMetric"] {{
    background-color: {COLOR_PANEL_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 10px 14px;
}}

.qfx-badge {{
    display:inline-block; padding:3px 10px; border-radius:4px;
    font-weight:700; font-size:10px; letter-spacing:0.5px;
}}

.js-plotly-plot .plotly .gtitle,
.js-plotly-plot .plotly .xtitle,
.js-plotly-plot .plotly .ytitle,
.js-plotly-plot .plotly .legendtext,
.js-plotly-plot .plotly .xtick text,
.js-plotly-plot .plotly .ytick text,
.js-plotly-plot .plotly .annotation text {{
    font-size: 10px !important;
}}

@keyframes signalBlink {{
    0% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.15; transform: scale(1.18); }}
    100% {{ opacity: 1; transform: scale(1); }}
}}

.js-plotly-plot svg path[fill="{COLOR_PB_BUY}"],
.js-plotly-plot svg path[stroke="{COLOR_PB_BUY}"],
.js-plotly-plot svg text[fill="{COLOR_PB_BUY}"],
.js-plotly-plot svg path[fill="{COLOR_PB_SELL}"],
.js-plotly-plot svg path[stroke="{COLOR_PB_SELL}"],
.js-plotly-plot svg text[fill="{COLOR_PB_SELL}"] {{
    animation: signalBlink 1.1s infinite ease-in-out;
    transform-origin: center;
}}
</style>
""",
    unsafe_allow_html=True,
)

# =====================================================================
# TELEGRAM CONFIG
# =====================================================================

TG_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".qfx_telegram_config.json")

def load_telegram_config():
    try:
        if os.path.exists(TG_CONFIG_PATH):
            with open(TG_CONFIG_PATH, "r") as f:
                data = json.load(f)
            return data.get("tg_token", ""), data.get("tg_chat", "")
    except Exception:
        pass
    return "", ""

def save_telegram_config(token, chat_id):
    try:
        with open(TG_CONFIG_PATH, "w") as f:
            json.dump({"tg_token": token, "tg_chat": chat_id}, f)
        return True, "Saved."
    except Exception as e:
        return False, str(e)

def send_telegram_alert(message, token, chat_id):
    token = (token or "").strip()
    chat_id = (chat_id or "").strip()

    if not token or not chat_id:
        return False, "Bot Token or Chat ID is missing."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}

    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        if data.get("ok"):
            return True, "Success"
        return False, data.get("description", "Unknown Telegram API error")
    except Exception as e:
        return False, str(e)
# =====================================================================
# DATA FETCH
# =====================================================================

@st.cache_data(ttl=300, show_spinner=False)
def fetch_live_ohlc(symbol="GC=F", period="6mo", interval="1d"):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_top_n_movers(symbols_tuple, n=1):
    symbols = list(symbols_tuple)
    tickers = [s for s, _ in symbols]

    if not tickers:
        return []

    try:
        data = yf.download(
            tickers,
            period="5d",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True
        )
    except Exception:
        return []

    results = []

    for sym, disp in symbols:
        try:
            sub = data[sym] if len(tickers) > 1 else data
            closes = sub["Close"].dropna()

            if len(closes) < 2:
                continue

            last_price = float(closes.iloc[-1])
            prev_price = float(closes.iloc[-2])

            if prev_price == 0:
                continue

            chg = (last_price - prev_price) / prev_price * 100

            results.append({
                "symbol": sym,
                "display": disp,
                "price": last_price,
                "chg": chg
            })

        except Exception:
            continue

    results.sort(key=lambda r: r["chg"], reverse=True)
    return results[:n]


# =====================================================================
# ORACLE SCORE (UPDATED TO EMA 9 / EMA 20)
# =====================================================================

def evaluate_oracle_score(symbol, display=None):
    try:
        df = fetch_live_ohlc(symbol, period="1y", interval="1d")
        if df.empty:
            return None

        last_close = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2]) if len(df) > 1 else last_close
        chg = ((last_close - prev_close) / prev_close) * 100

        recent = df.tail(30) if len(df) >= 30 else df
        high = float(recent["High"].max())
        low = float(recent["Low"].min())

        # ATR
        daily = df.resample("1D").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last"
        }).dropna()

        atr_source = daily if len(daily) >= 21 else df

        tr1 = atr_source["High"] - atr_source["Low"]
        tr2 = (atr_source["High"] - atr_source["Close"].shift(1)).abs()
        tr3 = (atr_source["Low"] - atr_source["Close"].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(21).mean().iloc[-1]
        if np.isnan(atr) or atr <= 0:
            atr = last_close * 0.02

        atr_pct = (atr / last_close) * 100

        # Volume expansion
        if "Volume" in df.columns and df["Volume"].notna().any():
            vol_series = df["Volume"].replace(0, np.nan)
            vol_avg = vol_series.rolling(20, min_periods=5).mean().iloc[-1]
            last_vol = vol_series.iloc[-1]

            if np.isnan(last_vol):
                last_vol = vol_avg

            vol_ratio = (last_vol / vol_avg) if vol_avg and not np.isnan(vol_avg) and vol_avg > 0 else 1.0
        else:
            vol_ratio = 1.0

        vol_ratio = min(max(float(vol_ratio), 0.5), 3.0)

        sig = "BUY" if chg >= 0 else "SELL"

        momentum_ratio = min(abs(chg) / max(atr_pct, 0.01), 2.0)

        expansion = 1.0 + (vol_ratio - 1.0) * 0.4 + momentum_ratio * 0.25
        expansion = min(max(expansion, 0.7), 2.2)

        tp1_mult = 2.0 * expansion
        tp2_mult = 4.0 * expansion

        sl = low * 0.98 if sig == "BUY" else high * 1.02
        tp1 = last_close + tp1_mult * atr if sig == "BUY" else last_close - tp1_mult * atr
        tp2 = last_close + tp2_mult * atr if sig == "BUY" else last_close - tp2_mult * atr

        tp1_pct = abs((tp1 - last_close) / last_close) * 100
        tp2_pct = abs((tp2 - last_close) / last_close) * 100

        momentum_score = min(momentum_ratio / 2.0, 1.0) * 40
        reward_score = min(tp1_pct / 8.0, 1.0) * 40
        volume_score = min(vol_ratio / 2.0, 1.0) * 20

        score_val = min(max(momentum_score + reward_score + volume_score, 0), 100)
        score_str = f"{score_val:.1f}%"

        # Renko structure (EMA9/20)
        renko_df, _ = build_atr_renko_df(df, atr_period=21, atr_multiplier=3.0,
                                         ema_fast=9, ema_slow=20,
                                         macd_fast=12, macd_slow=26, macd_signal=9,
                                         rsi_period=14)

        structure_event = latest_structure_event(renko_df, lookback=15)
        structure_label = structure_event["label"] if structure_event else "—"
        structure_type = structure_event["type"] if structure_event else None

        return {
            "Ticker": display or symbol,
            "RawSymbol": symbol,
            "Price": f"${format_price(last_close)}",
            "ChangePct": f"{chg:+.2f}%",
            "RawChange": chg,
            "DayHigh": f"${format_price(high)}",
            "DayLow": f"${format_price(low)}",
            "Signal": sig,
            "Structure": structure_label,
            "StructureType": structure_type,
            "Score": score_str,
            "SL": f"${format_price(sl)}",
            "TP1": f"${format_price(tp1)}",
            "TP1_PCT": f"{tp1_pct:.2f}%",
            "TP2": f"${format_price(tp2)}"
        }

    except Exception:
        return None


# =====================================================================
# 7-DAY OUTLOOK (UPDATED TO EMA 9 / EMA 20)
# =====================================================================

def compute_7day_outlook(symbol, display, period="1y", interval="1d"):
    try:
        data = fetch_live_ohlc(symbol, period=period, interval=interval)
        if data.empty or len(data) < 30:
            return None

        close = data["Close"]
        high = data["High"]
        low = data["Low"]

        ema9 = close.ewm(span=9, adjust=False).mean()
        ema20 = close.ewm(span=20, adjust=False).mean()

        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        macd_signal = macd.ewm(span=9, adjust=False).mean()

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(21).mean()

        last_close = float(close.iloc[-1])
        last_ema9 = float(ema9.iloc[-1])
        last_ema20 = float(ema20.iloc[-1])

        last_atr = float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else last_close * 0.02
        atr_pct = (last_atr / last_close) * 100

        idx = data.index

        if len(idx) > 5:
            deltas_minutes = np.diff(idx[-30:].values).astype("timedelta64[m]").astype(float)
            deltas_minutes = deltas_minutes[deltas_minutes > 0]
            avg_bar_minutes = float(np.median(deltas_minutes)) if len(deltas_minutes) else 1440.0
        else:
            avg_bar_minutes = 1440.0

        bars_in_7_days = max((7 * 24 * 60) / avg_bar_minutes, 1.0)

        reasons = []
        bias_score = 0.0

        if last_ema9 > last_ema20:
            bias_score += 1
            reasons.append(f"EMA9 (${format_price(last_ema9)}) is above EMA20 (${format_price(last_ema20)}), trend bullish.")
        else:
            bias_score -= 1
            reasons.append(f"EMA9 (${format_price(last_ema9)}) is below EMA20 (${format_price(last_ema20)}), trend bearish.")

        renko_df, _ = build_atr_renko_df(
            data, atr_period=21, atr_multiplier=3.0,
            ema_fast=9, ema_slow=20,
            macd_fast=12, macd_slow=26, macd_signal=9,
            rsi_period=14
        )

        structure_event = None
        structure_trend = None

        if not renko_df.empty and "Structure" in renko_df.columns:
            structure_trend = renko_df["Trend"].iloc[-1]
            structure_event = latest_structure_event(renko_df, lookback=15)

            structure_weight = {
                "BOS_DEMAND": 1.2,
                "BOS_SUPPLY": -1.2,
                "CHOCH_DEMAND": 1.8,
                "CHOCH_SUPPLY": -1.8,
            }

            if structure_event:
                s_type = structure_event["type"]
                s_level = structure_event["level"]
                bars_ago = structure_event["bars_ago"]

                bias_score += structure_weight.get(s_type, 0.0)

                recency = "latest brick" if bars_ago == 0 else f"{bars_ago} bricks ago"
                reasons.append(f"Structure {structure_event['label']} confirmed at ${format_price(s_level)} ({recency}).")

        direction = (
            "Bullish" if bias_score >= 2.0
            else "Bearish" if bias_score <= -2.0
            else "Neutral / Consolidation"
        )

        weekly_move_pct = atr_pct * np.sqrt(bars_in_7_days)
        tilt = float(np.clip(bias_score / 3.0, -1, 1))
        center_shift_pct = weekly_move_pct * 0.35 * tilt

        range_low = last_close * (1 - weekly_move_pct / 100 + center_shift_pct / 100)
        range_high = last_close * (1 + weekly_move_pct / 100 + center_shift_pct / 100)

        return {
            "display": display,
            "direction": direction,
            "bias_score": bias_score,
            "last_close": last_close,
            "range_low": min(range_low, range_high),
            "range_high": max(range_low, range_high),
            "reasons": reasons,
            "structure_event": structure_event,
            "structure_trend": structure_trend,
        }

    except Exception:
        return None


# =====================================================================
# WATCHLISTS (US100 + NIFTY200 + COMMODITIES + FOREX)
# =====================================================================

nifty200_raw = [
    "ABB","ABFRL","ACC","ADANIENSOL","ADANIENT","ADANIGREEN","ADANIPORTS","ADANIPOWER",
    "AFFLE","ALKEM","AMBER","APLAPOLLO","APOLLOHOSP","APOLLOTYRE","ASIANPAINT","ASTRAL",
    "AUBANK","AXISBANK","BAJAJFINSV","BAJAJHFL","BAJAJHLDNG","BAJAJ_AUTO","BAJFINANCE",
    "BANDHANBNK","BANKBARODA","BANKINDIA","BATAINDIA","BERGEPAINT","BHARATFORG",
    "BHARTIARTL","BHEL","BIOCON","BOSCHLTD","BPCL","BRITANNIA","BSE","CANBK","CANFINHOME",
    "CDSL","CEATLTD","CGPOWER","CHOLAFIN","CIPLA","CNX200","COALINDIA","COCHINSHIP",
    "COFORGE","COLPAL","CONCOR","COROMANDEL","CUMMINSIND","DALBHARAT","DEEPAKNTR",
    "DIVISLAB","DIXON","DLF","DMART","DRREDDY","EICHERMOT","ESCORTS","EVEREADY",
    "EXIDEIND","FACT","FEDERALBNK","FLUOROCHEM","FORTIS","GLENMARK","GODREJCP",
    "GODREJPROP","GOLDBEES","GRASIM","HAL","HAVELLS","HCLTECH","HDFCAMC","HDFCBANK",
    "HDFCGOLD","HDFCLIFE","HDFCSILVER","HEROMOTOCO","HINDALCO","HINDPETRO","ICICIBANK",
    "ICICIGI","ICICIPRULI","IDFCFIRSTB","IEX","IGL","INDHOTEL","INDIANB","INDIGO",
    "INDUSINDBK","INDUSTOWER","INFY","IOC","IPCALAB","IRCTC","IREDA","IRFC","ITC",
    "JINDALSTEL","JIOFIN","JKCEMENT","JSWENERGY","JSWSTEEL","JUBLFOOD","KOTAKBANK",
    "KPITTECH","LALPATHLAB","LAURUSLABS","LICHSGFIN","LICI","LINDEINDIA","LODHA","LT",
    "LTIM","LTTS","LUPIN","M&M","M&MFIN","MARICO","MARUTI","MAXHEALTH","MAZDOCK","MCX",
    "MFSL","MOTHERSON","MPHASIS","MRF","MSUMI","MUTHOOTFIN","NATIONALUM","NAUKRI",
    "NAVINFLUOR","NELCO","NESTLEIND","NHPC","NIFTY","NMDC","NTPC","OBEROIRLTY","OIL",
    "ONGC","PAGEIND","PATANJALI","PAYTM","PERSISTENT","PETRONET","PFC","PGHH",
    "PIDILITIND","PIIND","PNB","PNBHOUSING","POLICYBZR","POLYCAB","POONAWALLA",
    "POWERGRID","POWERINDIA","PRESTIGE","RAILTEL","RAMCOCEM","RECLTD","RELIANCE",
    "ROUTE","RVNL","SAIL","SBICARD","SBILIFE","SBIN","SHREECEM","SHRIRAMFIN","SIEMENS",
    "SONACOMS","SRF","SUNPHARMA","SUNTV","SYNGENE","TANLA","TATACHEM","TATACOMM",
    "TATACONSUM","TATAELXSI","TATAPOWER","TATASTEEL","TATATECH","TCS","TECHM",
    "TEJASNET","TIINDIA","TITAN","TMPV","TORNTPHARM","TORNTPOWER","TRENT","TVSMOTOR",
    "UBL","ULTRACEMCO","UNITDSPR","VBL","VEDL","VOLTAS","HINDCOPPER","NDIA"
]

us100_raw = [
    "PLTR","ARM","INTC","AMD","MU","QCOM","LRCX","MCHP","AVGO","AMAT","GFS","TXN",
    "IDXX","DDOG","ZS","TRI","CSCO","ADI","PANW","ORCL","AXON","CRWD","ASML","SLV",
    "CHTR","TTD","SHOP","NAS100","APP","BIIB","FUTU","PCAR","NVDA","FTNT","MSFT",
    "FAST","VRTX","US30","WDAY","CDNS","SPX","ORLY","ON","CSX","TSLA","AAPL","SBUX",
    "GLD","ADBE","PDD","LIN","BKR","GOOGL","HON","PYPL","INTU","ADSK","CMCSA","DASH",
    "ROST","GILD","KHC","CTAS","AEP","EA","DXCM","XEL","GEHC","BKNG","MDLZ","EXC",
    "WBD","MNST","LULU","TMUS","PEP","ADP","NFLX","ABNB","COST","CTSH","MELI","TTWO",
    "META","CSGP","CEG","AMZN","ISRG","CCEP","FANG"
]

nifty200_yf = [f"{t}.NS" for t in nifty200_raw]
def convert_us100_symbol(t):
    if t == "NAS100":
        return "^NDX"
    if t == "SPX":
        return "^GSPC"
    if t == "US30":
        return "^DJI"
    return t

# =====================================================================
# SCREENER LOGIC (EMA 9 / EMA 20)
# =====================================================================

def passes_quantfx_screener(df):
    """Apply EMA9/EMA20 + MACD + RSI + Structure + Trend + Volume + Volatility + 52W filters."""
    if df is None or df.empty or len(df) < 200:
        return False

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    vol = df["Volume"]

    # EMA 9 / EMA 20
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    sma200 = close.rolling(200).mean()

    # EMA crossover (BUY)
    if not (ema9.iloc[-1] > ema20.iloc[-1] and ema9.iloc[-2] <= ema20.iloc[-2]):
        return False

    # MACD
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    macd_signal = macd.ewm(span=9, adjust=False).mean()

    if not (macd.iloc[-1] > macd_signal.iloc[-1] and macd.iloc[-2] <= macd_signal.iloc[-2]):
        return False

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    if not (25 < rsi.iloc[-1] < 75):
        return False

    # Structure approximation (BOS/CHOCH)
    if not (close.iloc[-1] > high.shift(20).iloc[-1]):
        return False

    # Trend alignment
    if not (close.iloc[-1] > ema9.iloc[-1] and close.iloc[-1] > ema20.iloc[-1] and close.iloc[-1] > sma200.iloc[-1]):
        return False

    # Volume expansion
    if not (vol.iloc[-1] > vol.rolling(20).mean().iloc[-1]):
        return False

    # Volatility filter
    if ((high.iloc[-1] - low.iloc[-1]) / close.iloc[-1]) * 100 >= 5:
        return False

    return True


# =====================================================================
# SCREENER RUNNER FOR US100 + NIFTY200
# =====================================================================

def run_us100_nifty200_screener():
    results = []

    # Combine both watchlists
    watchlist = WATCHLIST_CATEGORIES["US100"] + WATCHLIST_CATEGORIES["Nifty200"]

    for symbol, display in watchlist:
        df = fetch_live_ohlc(symbol, period="6mo", interval="1d")
        if df is None or df.empty:
            continue

        if passes_quantfx_screener(df):
            last_price = format_price(df["Close"].iloc[-1])
            results.append({
                "display": display,
                "symbol": symbol,
                "price": last_price
            })

    return results
# =====================================================================
# CLICK-TO-CHART NAVIGATION
# =====================================================================

def go_to_chart(symbol):
    """Store selected symbol in session state and switch to chart view."""
    st.session_state["selected_symbol"] = symbol
    st.session_state["view"] = "📊 Charts"


# =====================================================================
# RIGHT-SIDE SCREENER BOXES (US100 + Nifty200)
# =====================================================================

def render_screener_sidebar():
    """Render screener results in right-side boxes, clickable to open chart."""

    st.markdown("### 🔍 Screener Matches (US100 + Nifty200)")
    st.markdown("<div style='margin-bottom:10px'></div>", unsafe_allow_html=True)

    results = run_us100_nifty200_screener()

    if not results:
        st.markdown(
            "<span style='color:#9FA8C3; font-size:12px;'>No matches found.</span>",
            unsafe_allow_html=True
        )
        return

    for item in results:
        display = item["display"]
        symbol = item["symbol"]
        price = item["price"]

        # Clickable HTML box
        box_html = f"""
        <div style="
            padding:12px;
            margin-bottom:10px;
            border:1px solid #202635;
            border-radius:6px;
            background:#11151C;
            cursor:pointer;
        "
        onclick="window.location.href='/?symbol={symbol}&view=📊 Charts'">

            <div style="font-size:13px; font-weight:700; color:#E5E9F0;">
                {display}
            </div>

            <div style="font-size:11px; color:#9FA8C3;">
                Price: {price}
            </div>
        </div>
        """

        st.markdown(box_html, unsafe_allow_html=True)
# =====================================================================
# CHART FIGURE (EMA9/20 + Renko + HA + MACD + RSI)
# =====================================================================

def create_chart_figure(renko_df, ha_df, brick_size, display, ema_fast=9, ema_slow=20):
    x = list(range(len(renko_df)))

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True,
        row_heights=[0.33, 0.33, 0.165, 0.165],
        vertical_spacing=0.05,
        subplot_titles=(
            f"{display} — Heikin Ashi (EMA9/20)",
            f"{display} — ATR Renko (brick ≈ {format_price(brick_size)})",
            "MACD",
            "RSI"
        ),
    )

    # -----------------------------
    # ROW 1 — HEIKIN ASHI
    # -----------------------------
    fig.add_trace(go.Candlestick(
        x=x,
        open=ha_df["Open"], high=ha_df["High"],
        low=ha_df["Low"], close=ha_df["Close"],
        increasing_line_color=COLOR_BULL,
        decreasing_line_color=COLOR_BEAR,
        increasing_fillcolor=COLOR_BULL,
        decreasing_fillcolor=COLOR_BEAR,
        name="Heikin Ashi",
        showlegend=False
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=x, y=ha_df["EMA_FAST"],
        line=dict(color=COLOR_MA_FAST, width=1.5),
        name=f"EMA {ema_fast}"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=x, y=ha_df["EMA_SLOW"],
        line=dict(color=COLOR_MA_SLOW, width=1.5),
        name=f"EMA {ema_slow}"
    ), row=1, col=1)

    # HA Buy/Sell dots
    ha_buy = [i for i in x if ha_df["Signal"].iloc[i] == "BUY"]
    ha_sell = [i for i in x if ha_df["Signal"].iloc[i] == "SELL"]

    fig.add_trace(go.Scatter(
        x=ha_buy,
        y=[ha_df["Low"].iloc[i] * 0.995 for i in ha_buy],
        mode="markers",
        marker=dict(color=COLOR_PB_BUY, size=10, symbol="circle"),
        name="HA BUY"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=ha_sell,
        y=[ha_df["High"].iloc[i] * 1.005 for i in ha_sell],
        mode="markers",
        marker=dict(color=COLOR_PB_SELL, size=10, symbol="circle"),
        name="HA SELL"
    ), row=1, col=1)

    # -----------------------------
    # ROW 2 — ATR RENKO
    # -----------------------------
    fig.add_trace(go.Candlestick(
        x=x,
        open=renko_df["Open"], high=renko_df["High"],
        low=renko_df["Low"], close=renko_df["Close"],
        increasing_line_color=COLOR_BULL,
        decreasing_line_color=COLOR_BEAR,
        increasing_fillcolor=COLOR_BULL,
        decreasing_fillcolor=COLOR_BEAR,
        name="Renko",
        showlegend=False
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=x, y=renko_df["EMA_FAST"],
        line=dict(color=COLOR_MA_FAST, width=1.5),
        name=f"EMA {ema_fast}"
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=x, y=renko_df["EMA_SLOW"],
        line=dict(color=COLOR_MA_SLOW, width=1.5),
        name=f"EMA {ema_slow}"
    ), row=2, col=1)

    # Renko BUY/SELL
    renko_buy = [i for i in x if renko_df["Confirmed_Signal"].iloc[i] == "BUY"]
    renko_sell = [i for i in x if renko_df["Confirmed_Signal"].iloc[i] == "SELL"]

    fig.add_trace(go.Scatter(
        x=renko_buy,
        y=[renko_df["Low"].iloc[i] - brick_size * 0.3 for i in renko_buy],
        mode="markers",
        marker=dict(color=COLOR_PB_BUY, size=12, symbol="triangle-up"),
        name="Renko BUY"
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=renko_sell,
        y=[renko_df["High"].iloc[i] + brick_size * 0.3 for i in renko_sell],
        mode="markers",
        marker=dict(color=COLOR_PB_SELL, size=12, symbol="triangle-down"),
        name="Renko SELL"
    ), row=2, col=1)

    # -----------------------------
    # ROW 3 — MACD
    # -----------------------------
    fig.add_trace(go.Bar(
        x=x,
        y=renko_df["MACD_Hist"],
        marker_color=COLOR_MACD_LINE,
        name="MACD Hist"
    ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=x, y=renko_df["MACD"],
        line=dict(color=COLOR_MACD_LINE, width=1.5),
        name="MACD"
    ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=x, y=renko_df["MACD_Signal"],
        line=dict(color=COLOR_SIGNAL_LINE, width=1.5),
        name="Signal"
    ), row=3, col=1)

    # -----------------------------
    # ROW 4 — RSI
    # -----------------------------
    fig.add_trace(go.Scatter(
        x=x, y=renko_df["RSI"],
        line=dict(color=COLOR_GREEN, width=1.5),
        name="RSI"
    ), row=4, col=1)

    fig.update_layout(
        height=900,
        showlegend=False,
        margin=dict(l=40, r=40, t=40, b=40),
        paper_bgcolor=COLOR_BG_DARK,
        plot_bgcolor=COLOR_BG_DARK
    )

    return fig


# =====================================================================
# MAIN VIEW HANDLER
# =====================================================================

def render_chart_view():
    symbol = st.session_state.get("selected_symbol", "GC=F")
    display = DISPLAY_TO_SYMBOL.get(symbol, symbol)

    df = fetch_live_ohlc(symbol, period="6mo", interval="1d")
    if df.empty:
        st.error("No data available.")
        return

    ha_df = compute_heikin_ashi(df, ema_fast=9, ema_slow=20)
    renko_df, brick_size = build_atr_renko_df(df, ema_fast=9, ema_slow=20)

    fig = create_chart_figure(renko_df, ha_df, brick_size, display)
    st.plotly_chart(fig, use_container_width=True)


def render_outlook_view():
    symbol = st.session_state.get("selected_symbol", "GC=F")
    display = DISPLAY_TO_SYMBOL.get(symbol, symbol)

    outlook = compute_7day_outlook(symbol, display)
    if not outlook:
        st.error("Outlook unavailable.")
        return

    st.markdown(f"### 🧭 7-Day Outlook — {display}")
    st.markdown(f"**Trend:** {outlook['direction']}")
    st.markdown(f"**Bias Score:** {outlook['bias_score']:.2f}")
    st.markdown(f"**Expected Range:** {format_price(outlook['range_low'])} — {format_price(outlook['range_high'])}")

    st.markdown("#### Reasons:")
    for r in outlook["reasons"]:
        st.markdown(f"- {r}")


def render_screener_view():
    st.markdown("### 🔍 Screener — US100 + Nifty200")
    results = run_us100_nifty200_screener()

    if not results:
        st.info("No screener matches.")
        return

    for item in results:
        if st.button(f"{item['display']} — {item['price']}"):
            go_to_chart(item["symbol"])
            st.experimental_rerun()


# =====================================================================
# MAIN LAYOUT
# =====================================================================

def render_main_layout():
    view = st.session_state.get("view", "📊 Charts")

    col_left, col_right = st.columns([0.75, 0.25])

    with col_left:
        if view == "📊 Charts":
            render_chart_view()
        elif view == "🧭 7-Day Outlook":
            render_outlook_view()
        elif view == "🔎 Scanner":
            render_screener_view()

    with col_right:
        render_screener_sidebar()
# =====================================================================
# SIDEBAR NAVIGATION
# =====================================================================

def render_sidebar():
    st.sidebar.title("QuantFX Terminal")

    # Default selected symbol
    if "selected_symbol" not in st.session_state:
        st.session_state["selected_symbol"] = "GC=F"

    # Default view
    if "view" not in st.session_state:
        st.session_state["view"] = "📊 Charts"

    # Sidebar symbol selector
    st.sidebar.subheader("Select Market")

    categories = list(WATCHLIST_CATEGORIES.keys())
    selected_category = st.sidebar.selectbox("Category", categories)

    symbols = WATCHLIST_CATEGORIES[selected_category]
    display_names = [disp for _, disp in symbols]

    selected_display = st.sidebar.selectbox("Symbol", display_names)
    selected_symbol = DISPLAY_TO_SYMBOL[selected_display]

    if st.sidebar.button("Load Chart"):
        st.session_state["selected_symbol"] = selected_symbol
        st.session_state["view"] = "📊 Charts"

    # Sidebar navigation
    st.sidebar.subheader("Navigation")
    nav_choice = st.sidebar.radio(
        "Go to",
        ["📊 Charts", "🧭 7-Day Outlook", "🔎 Scanner"],
        index=["📊 Charts", "🧭 7-Day Outlook", "🔎 Scanner"].index(st.session_state["view"])
    )

    st.session_state["view"] = nav_choice

    # Telegram config
    st.sidebar.subheader("Telegram Alerts")
    tg_token, tg_chat = load_telegram_config()

    new_token = st.sidebar.text_input("Bot Token", tg_token)
    new_chat = st.sidebar.text_input("Chat ID", tg_chat)

    if st.sidebar.button("Save Telegram Settings"):
        ok, msg = save_telegram_config(new_token, new_chat)
        if ok:
            st.sidebar.success(msg)
        else:
            st.sidebar.error(msg)


# =====================================================================
# MAIN APP WRAPPER
# =====================================================================

def main():
    render_sidebar()
    render_main_layout()


# =====================================================================
# RUN APP
# =====================================================================

if __name__ == "__main__":
    main()
