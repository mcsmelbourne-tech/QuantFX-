"""
QuantFX Terminal — ATR Renko & Macro Smart Money Structure
Streamlit rewrite with custom candle coloring, right-side axes, 
Heikin Ashi EMAs, single-fire pullback signals with blinking animation, 
blinking round dot buy/sell markers on Heikin Ashi & MACD, and targeted multi-market Telegram alerts.
"""
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
COLOR_MA_FAST = "#00FF66"
COLOR_MA_SLOW = "#FF3333"
COLOR_MACD_LINE = "#00FFCC"
COLOR_SIGNAL_LINE = "#FF66CC"
COLOR_ZERO_LINE = "#4C566A"
COLOR_BOS_DEMAND = "#26FF9A"
COLOR_BOS_SUPPLY = "#FF4F7B"
COLOR_CHOCH_DEMAND = "#00D4FF"
COLOR_CHOCH_SUPPLY = "#FF9900"

# Unique dedicated colors for blinking signals so CSS can target them precisely
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
        font-weight:700; font-size:12px; letter-spacing:0.5px;
    }}
    
    /* Blinking & Pulsing Animation for Buy / Sell Signals & Dots */
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
# TELEGRAM
# =====================================================================
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
# INDICATORS & HEIKIN ASHI / MACD
# =====================================================================
def compute_heikin_ashi(df, ema_fast=21, ema_slow=50):
    ha = pd.DataFrame(index=df.index)
    ha["Close"] = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4.0
    ha_open = [(df["Open"].iloc[0] + df["Close"].iloc[0]) / 2.0]
    for i in range(1, len(df)):
        ha_open.append((ha_open[i - 1] + ha["Close"].iloc[i - 1]) / 2.0)
    ha["Open"] = ha_open
    ha["High"] = pd.concat([df["High"], ha["Open"], ha["Close"]], axis=1).max(axis=1)
    ha["Low"] = pd.concat([df["Low"], ha["Open"], ha["Close"]], axis=1).min(axis=1)
    ha["EMA_FAST"] = ha["Close"].ewm(span=ema_fast, adjust=False).mean()
    ha["EMA_SLOW"] = ha["Close"].ewm(span=ema_slow, adjust=False).mean()
    
    # Compute HA Crossover Signals for Round Dots
    ha_signals = ["HOLD"] * len(ha)
    for i in range(1, len(ha)):
        if ha["EMA_FAST"].iloc[i] > ha["EMA_SLOW"].iloc[i] and ha["EMA_FAST"].iloc[i-1] <= ha["EMA_SLOW"].iloc[i-1]:
            ha_signals[i] = "BUY"
        elif ha["EMA_FAST"].iloc[i] < ha["EMA_SLOW"].iloc[i] and ha["EMA_FAST"].iloc[i-1] >= ha["EMA_SLOW"].iloc[i-1]:
            ha_signals[i] = "SELL"
    ha["Signal"] = ha_signals
    return ha

def detect_macd_crossovers(renko_df):
    macd = renko_df["MACD"].values
    signal = renko_df["MACD_Signal"].values
    macd_signals = ["HOLD"] * len(renko_df)
    macd_types = [None] * len(renko_df)
    if len(renko_df) < 2:
        return macd_signals, macd_types
    for i in range(1, len(renko_df)):
        if macd[i] > signal[i] and macd[i - 1] <= signal[i - 1]:
            macd_signals[i] = "BUY"
            macd_types[i] = "MACD Cross Up"
        elif macd[i] < signal[i] and macd[i - 1] >= signal[i - 1]:
            macd_signals[i] = "SELL"
            macd_types[i] = "MACD Cross Down"
    return macd_signals, macd_types

# =====================================================================
# SMART MONEY STRUCTURE — BOS & CHoCH
# =====================================================================
def detect_market_structure(high, low, close, swing_lookback=5, brick_type=None):
    high = pd.Series(high).reset_index(drop=True)
    low = pd.Series(low).reset_index(drop=True)
    close = pd.Series(close).reset_index(drop=True)
    n = len(close)
    is_high = [False] * n
    is_low = [False] * n
    if brick_type is not None:
        bt = list(brick_type)
        for i in range(n - 1):
            if bt[i] == "up" and bt[i + 1] == "down":
                is_high[i] = True
            elif bt[i] == "down" and bt[i + 1] == "up":
                is_low[i] = True
    else:
        lb = swing_lookback
        for i in range(lb, n - lb):
            window_h = high.iloc[i - lb:i + lb + 1]
            window_l = low.iloc[i - lb:i + lb + 1]
            if high.iloc[i] == window_h.max():
                is_high[i] = True
            if low.iloc[i] == window_l.min():
                is_low[i] = True
    structure = [None] * n
    level = [np.nan] * n
    trend_arr = [None] * n
    trend = None
    pending_high = None
    pending_high_idx = None
    pending_low = None
    pending_low_idx = None
    origin = [None] * n
    seq_arr = [None] * n
    seq = 0
    for i in range(n):
        c = float(close.iloc[i])
        broke_up = (
            pending_high is not None and pending_high_idx is not None
            and i > pending_high_idx and c > pending_high
        )
        broke_down = (
            pending_low is not None and pending_low_idx is not None
            and i > pending_low_idx and c < pending_low
        )
        if broke_up and broke_down:
            if abs(c - pending_high) <= abs(c - pending_low):
                broke_down = False
            else:
                broke_up = False
        if broke_up:
            is_choch = trend == "down"
            structure[i] = "CHOCH_DEMAND" if is_choch else "BOS_DEMAND"
            level[i] = pending_high
            origin[i] = pending_high_idx
            seq = 1 if (is_choch or seq <= 0) else seq + 1
            seq_arr[i] = seq
            trend = "up"
            pending_high = None
            pending_high_idx = None
        elif broke_down:
            is_choch = trend == "up"
            structure[i] = "CHOCH_SUPPLY" if is_choch else "BOS_SUPPLY"
            level[i] = pending_low
            origin[i] = pending_low_idx
            seq = 1 if (is_choch or seq <= 0) else seq + 1
            seq_arr[i] = seq
            trend = "down"
            pending_low = None
            pending_low_idx = None
        if is_high[i]:
            pending_high = float(high.iloc[i])
            pending_high_idx = i
        if is_low[i]:
            pending_low = float(low.iloc[i])
            pending_low_idx = i
        trend_arr[i] = trend
    return pd.DataFrame({
        "SwingHigh": is_high,
        "SwingLow": is_low,
        "Structure": structure,
        "StructureLevel": level,
        "StructureOriginIdx": origin,
        "StructureSeq": seq_arr,
        "Trend": trend_arr,
    })

STRUCTURE_LABELS = {
    "BOS_DEMAND": "B-S",
    "BOS_SUPPLY": "B-D",
    "CHOCH_DEMAND": "CH-S",
    "CHOCH_SUPPLY": "CH-D",
}

def latest_structure_event(struct_df, lookback=15):
    if struct_df is None or struct_df.empty or "Structure" not in struct_df.columns:
        return None
    tail = struct_df.tail(lookback)
    hits = tail[tail["Structure"].isin(["BOS_DEMAND", "BOS_SUPPLY", "CHOCH_DEMAND", "CHOCH_SUPPLY"])]
    if hits.empty:
        return None
    last_idx = hits.index[-1]
    s_type = hits["Structure"].iloc[-1]
    base_label = STRUCTURE_LABELS.get(s_type, s_type)
    return {
        "type": s_type,
        "label": base_label,
        "level": float(hits["StructureLevel"].iloc[-1]),
        "bars_ago": int((len(struct_df) - 1) - last_idx),
    }

def build_atr_renko_df(df,
                        atr_period=21,
                        atr_multiplier=3.0,
                        ema_fast=21,
                        ema_slow=50,
                        macd_fast=12,
                        macd_slow=26,
                        macd_signal=9,
                        rsi_period=14):
    if df.empty or len(df) < atr_period + 5:
        return pd.DataFrame(), 1.0
    closes = df["Close"]
    highs = df["High"]
    lows = df["Low"]
    dates = df.index
    tr1 = highs - lows
    tr2 = (highs - closes.shift(1)).abs()
    tr3 = (lows - closes.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()
    last_atr = atr.iloc[-1]
    if np.isnan(last_atr) or last_atr <= 0:
        last_atr = closes.iloc[-1] * 0.01
    brick_size = last_atr * atr_multiplier
    renko_rows = []
    current_brick_val = closes.iloc[0]
    for i in range(len(closes)):
        price = closes.iloc[i]
        dt = dates[i]
        diff = price - current_brick_val
        if abs(diff) >= brick_size:
            num_bricks = int(abs(diff) // brick_size)
            direction = 1 if diff > 0 else -1
            for _ in range(num_bricks):
                next_val = current_brick_val + direction * brick_size
                renko_rows.append({
                    "Date": dt,
                    "Open": current_brick_val,
                    "Close": next_val,
                    "High": max(current_brick_val, next_val),
                    "Low": min(current_brick_val, next_val),
                    "Type": "up" if direction > 0 else "down"
                })
                current_brick_val = next_val
    if not renko_rows:
        return pd.DataFrame(), brick_size
    renko_df = pd.DataFrame(renko_rows)
    renko_df.reset_index(drop=True, inplace=True)
    r_close = renko_df["Close"]
    renko_df["EMA_FAST"] = r_close.ewm(span=ema_fast, adjust=False).mean()
    renko_df["EMA_SLOW"] = r_close.ewm(span=ema_slow, adjust=False).mean()
    real_exp1 = closes.ewm(span=macd_fast, adjust=False).mean()
    real_exp2 = closes.ewm(span=macd_slow, adjust=False).mean()
    real_macd = real_exp1 - real_exp2
    real_macd_signal = real_macd.ewm(span=macd_signal, adjust=False).mean()
    macd_lookup = pd.DataFrame({
        "Date": dates,
        "MACD": real_macd.values,
        "MACD_Signal": real_macd_signal.values,
    }).sort_values("Date")
    renko_df = pd.merge_asof(
        renko_df.sort_values("Date").reset_index(drop=True),
        macd_lookup,
        on="Date",
        direction="backward",
    )
    delta = r_close.diff()
    gain = (delta.where(delta > 0, 0.0)).rolling(rsi_period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(rsi_period).mean()
    rs = gain / loss.replace(0, np.nan)
    renko_df["RSI"] = 100 - (100 / (1 + rs))

    signals = []
    pullback_signals = []
    pullback_fired = False
    current_trend = None

    for i in range(len(renko_df)):
        if i == 0:
            signals.append("HOLD")
            pullback_signals.append("HOLD")
            continue
            
        ema_fast_now = renko_df.loc[i, "EMA_FAST"]
        ema_slow_now = renko_df.loc[i, "EMA_SLOW"]
        ema_fast_prev = renko_df.loc[i - 1, "EMA_FAST"]
        ema_slow_prev = renko_df.loc[i - 1, "EMA_SLOW"]
        brick_type = renko_df.loc[i, "Type"]

        sig = "HOLD"
        pb_sig = "HOLD"

        if ema_fast_now > ema_slow_now and ema_fast_prev <= ema_slow_prev:
            sig = "BUY"
            current_trend = "BUY"
            pullback_fired = False
        elif ema_fast_now < ema_slow_now and ema_fast_prev >= ema_slow_prev:
            sig = "SELL"
            current_trend = "SELL"
            pullback_fired = False
        else:
            if ema_fast_now > ema_slow_now:
                if current_trend != "BUY":
                    current_trend = "BUY"
                    pullback_fired = False
                
                recent_types = renko_df.loc[max(0, i-3):i-1, "Type"].values
                if not pullback_fired and "down" in recent_types and brick_type == "up":
                    pb_sig = "BUY"
                    pullback_fired = True
            elif ema_fast_now < ema_slow_now:
                if current_trend != "SELL":
                    current_trend = "SELL"
                    pullback_fired = False

                recent_types = renko_df.loc[max(0, i-3):i-1, "Type"].values
                if not pullback_fired and "up" in recent_types and brick_type == "down":
                    pb_sig = "SELL"
                    pullback_fired = True

        signals.append(sig)
        pullback_signals.append(pb_sig)

    renko_df["Signal"] = signals
    renko_df["Pullback_Signal"] = pullback_signals

    macd_sigs, macd_types = detect_macd_crossovers(renko_df)
    renko_df["Div_Signal"] = macd_sigs
    renko_df["Div_Type"] = macd_types
    struct_df = detect_market_structure(
        renko_df["High"], renko_df["Low"], renko_df["Close"],
        swing_lookback=5, brick_type=renko_df["Type"]
    )
    renko_df = pd.concat(
        [renko_df.reset_index(drop=True), struct_df.reset_index(drop=True)], axis=1
    )
    return renko_df, brick_size

# =====================================================================
# DATA SOURCE & OUTLOOK
# =====================================================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_live_ohlc(symbol="GC=F", period="6mo", interval="1d"):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

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
        daily = df.resample("1D").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last"
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
        renko_df, _ = build_atr_renko_df(df, atr_period=21, atr_multiplier=3.0)
        structure_event = latest_structure_event(renko_df, lookback=15)
        structure_label = structure_event["label"] if structure_event else "—"
        structure_type = structure_event["type"] if structure_event else None
        is_fx = "=X" in symbol or symbol.startswith("FX:")
        decimals = 4 if is_fx else 2
        price_fmt = f"{last_close:,.{decimals}f}"
        high_fmt = f"{high:,.{decimals}f}"
        low_fmt = f"{low:,.{decimals}f}"
        if not is_fx:
            price_fmt = f"${price_fmt}"
            high_fmt = f"${high_fmt}"
            low_fmt = f"${low_fmt}"
        return {
            "Ticker": display or symbol,
            "RawSymbol": symbol,
            "Price": price_fmt,
            "ChangePct": f"{chg:+.2f}%",
            "RawChange": chg,
            "DayHigh": high_fmt,
            "DayLow": low_fmt,
            "Signal": sig,
            "Structure": structure_label,
            "StructureType": structure_type,
            "Score": score_str,
            "SL": f"{sl:,.{decimals}f}" if is_fx else f"${sl:,.{decimals}f}",
            "TP1": f"{tp1:,.{decimals}f}" if is_fx else f"${tp1:,.{decimals}f}",
            "TP1_PCT": f"{tp1_pct:.2f}%",
            "TP2": f"{tp2:,.{decimals}f}" if is_fx else f"${tp2:,.{decimals}f}"
        }
    except Exception:
        return None

def compute_7day_outlook(symbol, display, period="1y", interval="1d"):
    try:
        data = fetch_live_ohlc(symbol, period=period, interval=interval)
        if data.empty or len(data) < 30:
            return None
        close = data["Close"]
        high = data["High"]
        low = data["Low"]
        ema21 = close.ewm(span=21, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
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
        last_ema21, last_ema50 = float(ema21.iloc[-1]), float(ema50.iloc[-1])
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
        if last_ema21 > last_ema50:
            bias_score += 1
            reasons.append(f"EMA21 (${last_ema21:,.2f}) is above EMA50 (${last_ema50:,.2f}), keeping the trend bullish.")
        else:
            bias_score -= 1
            reasons.append(f"EMA21 (${last_ema21:,.2f}) is below EMA50 (${last_ema50:,.2f}), keeping the trend bearish.")
        renko_df, _ = build_atr_renko_df(
            data, atr_period=21, atr_multiplier=3.0,
            ema_fast=21, ema_slow=50,
            macd_fast=12, macd_slow=26, macd_signal=9,
            rsi_period=14
        )
        structure_event = None
        structure_trend = None
        if not renko_df.empty and "Structure" in renko_df.columns:
            structure_trend = renko_df["Trend"].iloc[-1]
            structure_event = latest_structure_event(renko_df, lookback=15)
            structure_weight = {
                "BOS_DEMAND": 1.2, "BOS_SUPPLY": -1.2,
                "CHOCH_DEMAND": 1.8, "CHOCH_SUPPLY": -1.8,
            }
            if structure_event:
                s_type = structure_event["type"]
                s_level = structure_event["level"]
                bars_ago = structure_event["bars_ago"]
                bias_score += structure_weight.get(s_type, 0.0)
                recency = "on the latest brick" if bars_ago == 0 else f"{bars_ago} bricks ago"
                reasons.append(f"Structure {structure_event['label']} confirmed at ${s_level:,.2f} ({recency}).")
        direction = "Bullish" if bias_score >= 2.0 else ("Bearish" if bias_score <= -2.0 else "Neutral / Consolidation")
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
# WATCHLISTS
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
us100_yf = [convert_us100_symbol(t) for t in us100_raw] + ["^IXIC"]
COMMODITIES = [("GC=F", "GOLD"), ("SI=F", "SILVER"), ("KC=F", "COFFEE"), ("CL=F", "CRUDE"), ("NG=F", "GAS")]
FOREX_PAIRS = [("EURUSD=X", "EUR/USD"), ("GBPUSD=X", "GBP/USD"), ("USDJPY=X", "USD/JPY"),
               ("AUDUSD=X", "AUD/USD"), ("USDCAD=X", "USD/CAD")]
WATCHLIST_CATEGORIES = {
    "Commodities": COMMODITIES,
    "Forex": FOREX_PAIRS,
    "Nifty200": list(zip(nifty200_yf, nifty200_raw)),
    "US100": list(zip(us100_yf, us100_raw + ["IXIC"])),
}
TIMEFRAME_PERIODS = {
    "15m": "10d", "30m": "20d", "60m": "60d",
    "4h": "180d", "1d": "1y", "1wk": "5y",
}

# =====================================================================
# CHARTING (Plotly — Renko, Heikin Ashi with Blinking Dots & Pullback Markers)
# =====================================================================
def render_charts(renko_df, ha_df, brick_size, display, ema_fast, ema_slow):
    x_renko = list(range(len(renko_df)))
    x_ha = list(range(len(ha_df)))
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=False,
        row_heights=[0.30, 0.32, 0.20, 0.18],
        vertical_spacing=0.035,
        subplot_titles=(
            f"{display} — Heikin Ashi (with Blinking Buy/Sell Dots & EMAs {ema_fast} & {ema_slow})",
            f"{display} — ATR Renko & Blinking Pullback Signals (brick ≈ {brick_size:,.4g})",
            "MACD (real price series with Blinking Crossover Dots)",
            "RSI",
        ),
    )
    # --- Row 1: Heikin Ashi candles + EMAs + Blinking Round Dot Buy/Sell Signals ---
    fig.add_trace(go.Candlestick(
        x=x_ha, open=ha_df["Open"], high=ha_df["High"], low=ha_df["Low"], close=ha_df["Close"],
        increasing_line_color=COLOR_BULL, decreasing_line_color=COLOR_BEAR,
        increasing_fillcolor=COLOR_BULL, decreasing_fillcolor=COLOR_BEAR,
        name="Heikin Ashi", showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=x_ha, y=ha_df["EMA_FAST"], line=dict(color=COLOR_MA_FAST, width=1.5),
        name=f"HA EMA {ema_fast}",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=x_ha, y=ha_df["EMA_SLOW"], line=dict(color=COLOR_MA_SLOW, width=1.5),
        name=f"HA EMA {ema_slow}",
    ), row=1, col=1)

    ha_buy_x = [i for i in range(len(ha_df)) if ha_df["Signal"].iloc[i] == "BUY"]
    ha_buy_y = [ha_df["Low"].iloc[i] * 0.995 for i in ha_buy_x]
    ha_sell_x = [i for i in range(len(ha_df)) if ha_df["Signal"].iloc[i] == "SELL"]
    ha_sell_y = [ha_df["High"].iloc[i] * 1.005 for i in ha_sell_x]

    if ha_buy_x:
        fig.add_trace(go.Scatter(
            x=ha_buy_x, y=ha_buy_y, mode="markers",
            marker=dict(color=COLOR_PB_BUY, size=11, symbol="circle"),
            name="HA Buy Dot",
        ), row=1, col=1)
    if ha_sell_x:
        fig.add_trace(go.Scatter(
            x=ha_sell_x, y=ha_sell_y, mode="markers",
            marker=dict(color=COLOR_PB_SELL, size=11, symbol="circle"),
            name="HA Sell Dot",
        ), row=1, col=1)

    # --- Row 2: ATR Renko candles + EMAs + Blinking Pullback Signals + Structure --
    fig.add_trace(go.Candlestick(
        x=x_renko, open=renko_df["Open"], high=renko_df["High"], low=renko_df["Low"], close=renko_df["Close"],
        increasing_line_color=COLOR_BULL, decreasing_line_color=COLOR_BEAR,
        increasing_fillcolor=COLOR_BULL, decreasing_fillcolor=COLOR_BEAR,
        name="ATR Renko", showlegend=False,
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=x_renko, y=renko_df["EMA_FAST"], line=dict(color=COLOR_MA_FAST, width=1.5),
        name=f"EMA {ema_fast}",
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=x_renko, y=renko_df["EMA_SLOW"], line=dict(color=COLOR_MA_SLOW, width=1.5),
        name=f"EMA {ema_slow}",
    ), row=2, col=1)

    pb_buy_x = [i for i in range(len(renko_df)) if renko_df["Pullback_Signal"].iloc[i] == "BUY"]
    pb_buy_y = [renko_df["Low"].iloc[i] - (brick_size * 0.5) for i in pb_buy_x]
    pb_sell_x = [i for i in range(len(renko_df)) if renko_df["Pullback_Signal"].iloc[i] == "SELL"]
    pb_sell_y = [renko_df["High"].iloc[i] + (brick_size * 0.5) for i in pb_sell_x]

    if pb_buy_x:
        fig.add_trace(go.Scatter(
            x=pb_buy_x, y=pb_buy_y, mode="markers+text",
            marker=dict(color=COLOR_PB_BUY, size=12, symbol="triangle-up"),
            text=["BUY"] * len(pb_buy_x), textposition="bottom center",
            textfont=dict(color=COLOR_PB_BUY, size=14),
            name="Pullback Buy Signal",
        ), row=2, col=1)

    if pb_sell_x:
        fig.add_trace(go.Scatter(
            x=pb_sell_x, y=pb_sell_y, mode="markers+text",
            marker=dict(color=COLOR_PB_SELL, size=12, symbol="triangle-down"),
            text=["SELL"] * len(pb_sell_x), textposition="top center",
            textfont=dict(color=COLOR_PB_SELL, size=14),
            name="Pullback Sell Signal",
        ), row=2, col=1)

    struct_style = {
        "BOS_DEMAND": (COLOR_BOS_DEMAND, "B-S"),
        "BOS_SUPPLY": (COLOR_BOS_SUPPLY, "B-D"),
        "CHOCH_DEMAND": (COLOR_CHOCH_DEMAND, "CH-S"),
        "CHOCH_SUPPLY": (COLOR_CHOCH_SUPPLY, "CH-D"),
    }
    for i in range(len(renko_df)):
        s_type = renko_df["Structure"].iloc[i]
        if s_type not in struct_style:
            continue
        color, label = struct_style[s_type]
        s_level = renko_df["StructureLevel"].iloc[i]
        origin_idx = renko_df["StructureOriginIdx"].iloc[i]
        span_start = int(origin_idx) if pd.notna(origin_idx) else max(i - 6, 0)
        fig.add_shape(
            type="line", x0=span_start, x1=i, y0=s_level, y1=s_level,
            line=dict(color=color, width=1.5, dash="dash"), opacity=0.6,
            row=2, col=1,
        )
        fig.add_annotation(
            x=i, y=s_level, text=label, showarrow=False,
            font=dict(color="#FFFFFF", size=10), bgcolor="#1E222D",
            bordercolor=color, borderwidth=1, row=2, col=1,
            yshift=14 if s_type in ("BOS_DEMAND", "CHOCH_DEMAND") else -14,
        )

    # --- Row 3: MACD + Blinking Round Dot Crossover Signals --------------
    fig.add_trace(go.Scatter(
        x=x_renko, y=renko_df["MACD"], line=dict(color=COLOR_MACD_LINE, width=1.6), name="MACD",
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=x_renko, y=renko_df["MACD_Signal"], line=dict(color=COLOR_SIGNAL_LINE, width=1.6), name="Signal",
    ), row=3, col=1)
    fig.add_hline(y=0, line=dict(color=COLOR_ZERO_LINE, width=1), row=3, col=1)

    macd_buy_x = [i for i in range(len(renko_df)) if renko_df["Div_Signal"].iloc[i] == "BUY"]
    macd_buy_y = [renko_df["MACD"].iloc[i] for i in macd_buy_x]
    macd_sell_x = [i for i in range(len(renko_df)) if renko_df["Div_Signal"].iloc[i] == "SELL"]
    macd_sell_y = [renko_df["MACD"].iloc[i] for i in macd_sell_x]

    if macd_buy_x:
        fig.add_trace(go.Scatter(
            x=macd_buy_x, y=macd_buy_y, mode="markers",
            marker=dict(color=COLOR_PB_BUY, size=10, symbol="circle"),
            name="MACD Cross Up Dot",
        ), row=3, col=1)
    if macd_sell_x:
        fig.add_trace(go.Scatter(
            x=macd_sell_x, y=macd_sell_y, mode="markers",
            marker=dict(color=COLOR_PB_SELL, size=10, symbol="circle"),
            name="MACD Cross Down Dot",
        ), row=3, col=1)

    # --- Row 4: RSI --------------------------------------------------------
    fig.add_trace(go.Scatter(
        x=x_renko, y=renko_df["RSI"], line=dict(color="#FFD700", width=1.5), name="RSI",
    ), row=4, col=1)
    fig.add_hline(y=70, line=dict(color=COLOR_RED, width=1, dash="dash"), row=4, col=1)
    fig.add_hline(y=30, line=dict(color=COLOR_GREEN, width=1, dash="dash"), row=4, col=1)
    fig.update_yaxes(range=[0, 100], row=4, col=1)

    fig.update_layout(
        height=980,
        paper_bgcolor=COLOR_BG_DARK,
        plot_bgcolor=COLOR_BG_DARK,
        font=dict(color=COLOR_TEXT_MUTED, size=11),
        legend=dict(orientation="h", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=10, r=10, t=50, b=10),
        xaxis_rangeslider_visible=False,
        xaxis2_rangeslider_visible=False,
    )
    for r in range(1, 5):
        fig.update_xaxes(showgrid=False, row=r, col=1)
        fig.update_yaxes(gridcolor="#2A2F3A", side="right", row=r, col=1)
    st.plotly_chart(fig, use_container_width=True, theme=None)

# =====================================================================
# SIDEBAR CONTROLS
# =====================================================================
st.sidebar.markdown("## 📈 QuantFX Terminal")
st.sidebar.caption("ATR Renko · Heikin Ashi · Pullback Signals")
symbol_mode = st.sidebar.radio("Symbol source", ["Presets", "Custom"], horizontal=True)
if symbol_mode == "Presets":
    preset_cat = st.sidebar.selectbox("Category", list(WATCHLIST_CATEGORIES.keys()))
    options = WATCHLIST_CATEGORIES[preset_cat]
    choice = st.sidebar.selectbox("Symbol", options, format_func=lambda t: t[1])
    current_symbol, current_display = choice
else:
    current_symbol = st.sidebar.text_input("Yahoo Finance symbol", value="GC=F")
    current_display = st.sidebar.text_input("Display name", value=current_symbol)

interval = st.sidebar.select_slider(
    "Timeframe", options=list(TIMEFRAME_PERIODS.keys()), value="1d"
)
period = TIMEFRAME_PERIODS[interval]

st.sidebar.markdown("---")
c1, c2 = st.sidebar.columns(2)
ema_fast = c1.number_input("EMA Fast", min_value=1, max_value=200, value=21)
ema_slow = c2.number_input("EMA Slow", min_value=1, max_value=200, value=50)
c3, c4 = st.sidebar.columns(2)
atr_period = c3.number_input("ATR Period", min_value=2, max_value=100, value=21)
atr_multiplier = c4.number_input("ATR Mult.", min_value=0.1, max_value=10.0, value=3.0, step=0.1)

st.sidebar.markdown("---")
with st.sidebar.expander("Telegram alerts"):
    tg_token = st.text_input("Bot Token", value=st.session_state.get("tg_token", ""), type="password")
    tg_chat = st.text_input("Chat ID", value=st.session_state.get("tg_chat", ""))
    st.session_state["tg_token"] = tg_token
    st.session_state["tg_chat"] = tg_chat
    if st.button("Send test alert"):
        ok, msg = send_telegram_alert(
            "🟢 *QuantFX Terminal Test Alert*\nConnection successfully established!", tg_token, tg_chat
        )
        st.success(msg) if ok else st.error(msg)

if st.sidebar.button("🔄 Refresh data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# =====================================================================
# AUTOMATED MULTI-MARKET TELEGRAM SCANNER & DISPATCHER
# =====================================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔔 Automated Triggers")
if st.sidebar.button("🚀 Run Rule-Based Telegram Scan", use_container_width=True):
    triggered_messages = []
    fx_comm_watchlist = [("Commodities", COMMODITIES), ("Forex", FOREX_PAIRS)]
    for cat_name, symbols in fx_comm_watchlist:
        for sym, disp in symbols:
            try:
                df = fetch_live_ohlc(sym, period="10d", interval="30m")
                if not df.empty:
                    renko_df, _ = build_atr_renko_df(df, atr_period=int(atr_period), atr_multiplier=float(atr_multiplier))
                    ev = latest_structure_event(renko_df, lookback=3)
                    if ev and ev["type"] in ["CHOCH_DEMAND", "CHOCH_SUPPLY", "BOS_DEMAND", "BOS_SUPPLY"]:
                        if ev["bars_ago"] <= 1:
                            triggered_messages.append(f"🚨 *[30m FX/Comm]* *{disp}* triggered *{ev['label']}* at `${ev['level']:,.4f}`")
            except Exception:
                continue

    if triggered_messages:
        combined_msg = "📢 *QuantFX Automated Triggers*\n\n" + "\n".join(triggered_messages)
        ok, m = send_telegram_alert(combined_msg, tg_token, tg_chat)
        if ok:
            st.sidebar.success(f"Dispatched {len(triggered_messages)} alert(s) via Telegram!")
        else:
            st.sidebar.error(f"Failed to send: {m}")
    else:
        st.sidebar.info("Scan completed: No new active triggers matching rules.")

# =====================================================================
# MAIN LAYOUT
# =====================================================================
st.markdown(
    f"<h2 style='color:#FFFFFF;margin-bottom:0;'>{current_display} "
    f"<span style='color:{COLOR_TEXT_MUTED};font-size:14px;'>({current_symbol}) · {interval}</span></h2>",
    unsafe_allow_html=True,
)
tab_chart, tab_outlook, tab_scanner = st.tabs(["📊 Charts", "🧭 7-Day Outlook", "🔎 Scanner"])

# ---- Charts tab --------------------------------------------------------
with tab_chart:
    with st.spinner(f"Fetching {current_display}..."):
        raw_df = fetch_live_ohlc(current_symbol, period=period, interval=interval)
    if raw_df.empty:
        st.error(f"No data returned for {current_display} ({current_symbol}).")
    else:
        renko_df, brick_size = build_atr_renko_df(
            raw_df, atr_period=atr_period, atr_multiplier=atr_multiplier,
            ema_fast=ema_fast, ema_slow=ema_slow,
        )
        if renko_df.empty:
            st.warning("Not enough data to build ATR Renko bricks for this timeframe — try a longer timeframe.")
        else:
            ha_df = compute_heikin_ashi(raw_df, ema_fast=ema_fast, ema_slow=ema_slow)
            last_close = float(raw_df["Close"].iloc[-1])
            prev_close = float(raw_df["Close"].iloc[-2]) if len(raw_df) > 1 else last_close
            chg_pct = ((float(raw_df["Close"].iloc[-1]) - prev_close) / prev_close) * 100 if prev_close else 0.0
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Last Close", f"{float(raw_df['Close'].iloc[-1]):,.4g}", f"{chg_pct:+.2f}%")
            m2.metric("Renko Bricks", len(renko_df))
            m3.metric("Brick Size", f"{brick_size:,.4g}")
            struct_event = latest_structure_event(renko_df, lookback=15)
            m4.metric("Latest Structure", struct_event["label"] if struct_event else "—")
            render_charts(renko_df, ha_df, brick_size, current_display, ema_fast, ema_slow)
            
            last_signal = renko_df["Signal"].iloc[-1]
            last_pullback = renko_df["Pullback_Signal"].iloc[-1]
            badge_color = COLOR_GREEN if "BUY" in last_signal or "BUY" in last_pullback else (COLOR_RED if "SELL" in last_signal or "SELL" in last_pullback else COLOR_TEXT_MUTED)
            
            st.markdown(
                f"EMA trend signal: <span class='qfx-badge' style='background:{badge_color}22;color:{badge_color};'>{last_signal}</span>"
                f"&nbsp;&nbsp;·&nbsp;&nbsp;Pullback Signal: <b>{last_pullback}</b>",
                unsafe_allow_html=True,
            )
            if st.button("📨 Send current signal to Telegram"):
                msg = (
                    f"*{current_display}* ({current_symbol})\n"
                    f"Price: {float(raw_df['Close'].iloc[-1]):,.4g}\n"
                    f"EMA Signal: {last_signal}\n"
                    f"Pullback Signal: {last_pullback}\n"
                    f"Structure: {struct_event['label'] if struct_event else '—'}"
                )
                ok, m = send_telegram_alert(msg, tg_token, tg_chat)
                st.success(m) if ok else st.error(m)

# ---- Outlook tab --------------------------------------------------------
with tab_outlook:
    with st.spinner("Computing 7-day outlook..."):
        outlook = compute_7day_outlook(current_symbol, current_display, period="1y", interval="1d")
    if outlook is None:
        st.warning("Not enough history to compute an outlook for this symbol.")
    else:
        dir_color = COLOR_GREEN if outlook["direction"] == "Bullish" else (
            COLOR_RED if outlook["direction"] == "Bearish" else COLOR_TEXT_MUTED
        )
        st.markdown(
            f"<span class='qfx-badge' style='background:{dir_color}22;color:{dir_color};font-size:16px;'>"
            f"{outlook['direction']}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"Projected 7-day macro range: **{outlook['range_low']:,.2f} – {outlook['range_high']:,.2f}** "
            f"(last close: {outlook['last_close']:,.2f})"
        )
        if outlook["structure_event"]:
            se = outlook["structure_event"]
            st.caption(f"Latest structure event: {se['label']} at {se['level']:,.2f} ({se['bars_ago']} bricks ago)")
        st.markdown("#### Reasoning")
        for r in outlook["reasons"]:
            st.markdown(f"- {r}")

# ---- Scanner tab --------------------------------------------------------
with tab_scanner:
    st.caption("Runs the oracle score across a watchlist.")
    cats = st.multiselect("Watchlists to scan", list(WATCHLIST_CATEGORIES.keys()), default=["Commodities", "Forex"])
    if st.button("▶️ Run scanner", type="primary"):
        if not cats:
            st.warning("Pick at least one watchlist.")
        else:
            results = []
            for cat in cats:
                for sym, disp in WATCHLIST_CATEGORIES[cat]:
                    res = evaluate_oracle_score(sym, disp)
                    if res:
                        results.append(res)
            df_res = pd.DataFrame(results)
            st.session_state["scanner_results"] = df_res
    df_res = st.session_state.get("scanner_results")
    if df_res is not None and not df_res.empty:
        display_cols = ["Ticker", "Price", "ChangePct", "Signal", "Structure", "Score", "SL", "TP1", "TP1_PCT", "TP2"]
        def _row_style(row):
            color = COLOR_GREEN if row["Signal"] == "BUY" else COLOR_RED
            return [f"color: {color}" if col == "Signal" else "" for col in row.index]
        st.dataframe(
            df_res[display_cols].style.apply(_row_style, axis=1),
            use_container_width=True, hide_index=True,
        )
    elif df_res is not None:
        st.info("No results — the data source may be rate-limiting or the symbols returned no data.")
