import sys
from datetime import datetime
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QLineEdit, QTextBrowser, QProgressBar,
    QSplitter, QSpinBox, QDialog, QFormLayout, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QKeySequence, QShortcut

# =====================================================================
# COLORS – TradingView‑style dark + neon
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

COLOR_MA9 = "#00FF66"
COLOR_MA20 = "#FF3333"

COLOR_MACD_LINE = "#00FFCC"
COLOR_SIGNAL_LINE = "#FF66CC"
COLOR_ZERO_LINE = "#4C566A"
COLOR_DARK_TEXT = "#000000"

# Market structure (BOS / CHoCH) overlay colors
COLOR_BOS_DEMAND = "#26FF9A"     # bullish continuation
COLOR_BOS_SUPPLY = "#FF4F7B"     # bearish continuation
COLOR_CHOCH_DEMAND = "#00D4FF"   # bullish reversal / structural flip
COLOR_CHOCH_SUPPLY = "#FF9900"   # bearish reversal / structural flip
COLOR_SWING_MARKER = "#9FA8C3"

BG_IMAGE_PATH = None

# Global Telegram Config Cache
TELEGRAM_CONFIG = {
    "token": "",
    "chat_id": ""
}

def send_telegram_alert(message):
    token = TELEGRAM_CONFIG.get("token", "").strip()
    chat_id = TELEGRAM_CONFIG.get("chat_id", "").strip()
    if not token or not chat_id:
        return False, "Bot Token or Chat ID is missing."
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        if data.get("ok"):
            return True, "Success"
        else:
            return False, data.get("description", "Unknown Telegram API error")
    except Exception as e:
        return False, str(e)

# =====================================================================
# TABLE ITEM
# =====================================================================
class NumericTableWidgetItem(QTableWidgetItem):
    def __init__(self, text):
        super().__init__(text)

    def __lt__(self, other):
        try:
            val1 = float(self.text().replace('$', '').replace('%', '').replace(',', ''))
            val2 = float(other.text().replace('$', '').replace('%', '').replace(',', ''))
            return val1 < val2
        except ValueError:
            return super().__lt__(other)

# =====================================================================
# INDICATORS & REFINED MACD CROSSOVER DETECTION
# =====================================================================
def compute_heikin_ashi(df):
    """Standard Heiken Ashi transform of an OHLC dataframe."""
    ha = pd.DataFrame(index=df.index)
    ha["Close"] = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4.0

    ha_open = [(df["Open"].iloc[0] + df["Close"].iloc[0]) / 2.0]
    for i in range(1, len(df)):
        ha_open.append((ha_open[i - 1] + ha["Close"].iloc[i - 1]) / 2.0)
    ha["Open"] = ha_open

    ha["High"] = pd.concat([df["High"], ha["Open"], ha["Close"]], axis=1).max(axis=1)
    ha["Low"] = pd.concat([df["Low"], ha["Open"], ha["Close"]], axis=1).min(axis=1)

    return ha

def detect_macd_crossovers(renko_df):
    """Detects robust MACD line and Signal line crossovers for Buy/Sell triggers."""
    macd = renko_df["MACD"].values
    signal = renko_df["MACD_Signal"].values
    
    macd_signals = ["HOLD"] * len(renko_df)
    macd_types = [None] * len(renko_df)

    if len(renko_df) < 2:
        return macd_signals, macd_types

    for i in range(1, len(renko_df)):
        # Bullish Crossover: MACD crosses above Signal line
        if macd[i] > signal[i] and macd[i - 1] <= signal[i - 1]:
            macd_signals[i] = "BUY"
            macd_types[i] = "MACD Cross Up"
        # Bearish Crossover: MACD crosses below Signal line
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

    # ---- MACD Calculation -------------------------------------------------
    # NOTE: MACD is intentionally computed from the *real*, time-indexed close
    # price series (df["Close"]), not from the Renko brick closes. Renko bricks
    # collapse a whole price history down to only as many rows as there are
    # bricks (often just a handful), which starves the 12/26/9 EMAs of data and
    # produces a MACD line that barely moves off a single smooth sweep — i.e.
    # it "looks flat". Computing MACD on the full-resolution close series gives
    # it enough data to actually oscillate and cross, and each Renko brick is
    # then stamped with the MACD/Signal value as of that brick's date.
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
    for i in range(len(renko_df)):
        if i == 0:
            signals.append("HOLD")
            continue

        ema_fast_now = renko_df.loc[i, "EMA_FAST"]
        ema_slow_now = renko_df.loc[i, "EMA_SLOW"]
        ema_fast_prev = renko_df.loc[i-1, "EMA_FAST"]
        ema_slow_prev = renko_df.loc[i-1, "EMA_SLOW"]

        buy = False
        sell = False

        if ema_fast_now > ema_slow_now and ema_fast_prev <= ema_slow_prev:
            buy = True
        elif ema_fast_now < ema_slow_now and ema_fast_prev >= ema_slow_prev:
            sell = True

        if buy:
            signals.append("BUY")
        elif sell:
            signals.append("SELL")
        else:
            signals.append("HOLD")

    renko_df["Signal"] = signals
    
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
        macd_hist = macd - macd_signal

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(21).mean()

        last_close = float(close.iloc[-1])
        last_ema21, last_ema50 = float(ema21.iloc[-1]), float(ema50.iloc[-1])
        prev_ema21, prev_ema50 = float(ema21.iloc[-2]), float(ema50.iloc[-2])
        last_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
        last_macd_hist = float(macd_hist.iloc[-1])
        prev_macd_hist = float(macd_hist.iloc[-2])
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

        ema21_slope_pct = 0.0
        if len(ema21) > 6 and float(ema21.iloc[-6]) != 0:
            ema21_slope_pct = ((last_ema21 - float(ema21.iloc[-6])) / float(ema21.iloc[-6])) * 100

        reasons = []
        bias_score = 0.0

        if last_ema21 > last_ema50:
            bias_score += 1
            reasons.append(f"EMA21 (${last_ema21:,.2f}) is above EMA50 (${last_ema50:,.2f}), keeping the trend bullish.")
            if prev_ema21 <= prev_ema50:
                bias_score += 1
                reasons.append("EMA21 just crossed above EMA50 - a fresh bullish crossover.")
        else:
            bias_score -= 1
            reasons.append(f"EMA21 (${last_ema21:,.2f}) is below EMA50 (${last_ema50:,.2f}), keeping the trend bearish.")
            if prev_ema21 >= prev_ema50:
                bias_score -= 1
                reasons.append("EMA21 just crossed below EMA50 - a fresh bearish crossover.")

        if ema21_slope_pct > 0.3:
            bias_score += 1
            reasons.append(f"Momentum is accelerating - EMA21 up {ema21_slope_pct:.1f}% over recent periods.")
        elif ema21_slope_pct < -0.3:
            bias_score -= 1
            reasons.append(f"Momentum is deteriorating - EMA21 down {abs(ema21_slope_pct):.1f}% over recent periods.")

        if last_rsi >= 70:
            bias_score -= 0.5
            reasons.append(f"RSI is elevated at {last_rsi:.0f}, cautioning potential pullbacks.")
        elif last_rsi <= 30:
            bias_score += 0.5
            reasons.append(f"RSI is oversold at {last_rsi:.0f}, hinting at potential rebound support.")
        else:
            reasons.append(f"RSI is neutral at {last_rsi:.0f}.")

        if last_macd_hist > 0 and last_macd_hist > prev_macd_hist:
            bias_score += 1
            reasons.append("MACD histogram is positive and expanding — macro bullish momentum building.")
        elif last_macd_hist < 0 and last_macd_hist < prev_macd_hist:
            bias_score -= 1
            reasons.append("MACD histogram is negative and expanding — macro bearish momentum building.")

        renko_df, _ = build_atr_renko_df(
            data, atr_period=21, atr_multiplier=3.0,
            ema_fast=21, ema_slow=50,
            macd_fast=12, macd_slow=26, macd_signal=9,
            rsi_period=14
        )
        if not renko_df.empty and len(renko_df) >= 2:
            last_renko_type = renko_df["Type"].iloc[-1]
            last_renko_close = float(renko_df["Close"].iloc[-1])
            renko_fast = float(renko_df["EMA_FAST"].iloc[-1])
            renko_slow = float(renko_df["EMA_SLOW"].iloc[-1])

            if renko_fast > renko_slow:
                bias_score += 0.5
                reasons.append(f"ATR Renko trend is bullish - fast EMA (${renko_fast:,.2f}) > slow EMA (${renko_slow:,.2f}).")
            else:
                bias_score -= 0.5
                reasons.append(f"ATR Renko trend is bearish - fast EMA (${renko_fast:,.2f}) < slow EMA (${renko_slow:,.2f}).")

            if last_renko_type == "up":
                bias_score += 0.5
                reasons.append(f"Latest Renko brick printed up at ${last_renko_close:,.2f}.")
            else:
                bias_score -= 0.5
                reasons.append(f"Latest Renko brick printed down at ${last_renko_close:,.2f}.")

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
                recency = "on the latest brick" if bars_ago == 0 else f"{bars_ago} bricks ago"
                if s_type == "CHOCH_DEMAND":
                    reasons.append(f"Bullish CH-S confirmed at ${s_level:,.2f} ({recency}) — major trend shift to demand.")
                elif s_type == "CHOCH_SUPPLY":
                    reasons.append(f"Bearish CH-D confirmed at ${s_level:,.2f} ({recency}) — major trend shift to supply.")
                elif s_type == "BOS_DEMAND":
                    reasons.append(f"Bullish B-S confirmed at ${s_level:,.2f} ({recency}) — macro demand continuation.")
                elif s_type == "BOS_SUPPLY":
                    reasons.append(f"Bearish B-D confirmed at ${s_level:,.2f} ({recency}) — macro supply continuation.")

        if bias_score >= 2.0:
            direction = "Bullish"
        elif bias_score <= -2.0:
            direction = "Bearish"
        else:
            direction = "Neutral / Consolidation"

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
            "last_ema9": last_ema21,
            "last_ema20": last_ema50,
            "last_rsi": last_rsi,
            "last_macd": float(macd.iloc[-1]),
            "last_macd_signal": float(macd_signal.iloc[-1]),
            "structure_event": structure_event,
            "structure_trend": structure_trend,
        }
    except Exception:
        return None

# =====================================================================
# LISTS
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

# =====================================================================
# WORKERS
# =====================================================================
class ScannerWorker(QThread):
    progress = pyqtSignal(int)
    resultReady = pyqtSignal(dict)

    def run(self):
        commodities = [
            ("GC=F", "GOLD"), ("SI=F", "SILVER"), ("KC=F", "COFFEE"),
            ("CL=F", "CRUDE"), ("NG=F", "GAS")
        ]
        forex_pairs = [
            ("EURUSD=X", "EUR/USD"), ("GBPUSD=X", "GBP/USD"),
            ("USDJPY=X", "USD/JPY"), ("AUDUSD=X", "AUD/USD"),
            ("USDCAD=X", "USD/CAD")
        ]

        comm_res = []
        forex_res = []
        nifty_res = []
        us100_res = []

        total = len(commodities) + len(forex_pairs) + len(nifty200_yf) + len(us100_yf)
        count = 0

        for s, d in commodities:
            res = evaluate_oracle_score(s, display=d)
            if res:
                comm_res.append(res)
            count += 1
            self.progress.emit(int((count / total) * 100))

        for s, d in forex_pairs:
            res = evaluate_oracle_score(s, display=d)
            if res:
                forex_res.append(res)
            count += 1
            self.progress.emit(int((count / total) * 100))

        for yf_sym, disp in zip(nifty200_yf, nifty200_raw):
            res = evaluate_oracle_score(yf_sym, display=disp)
            if res:
                nifty_res.append(res)
            count += 1
            self.progress.emit(int((count / total) * 100))

        for yf_sym, disp in zip(us100_yf, us100_raw + ["IXIC"]):
            res = evaluate_oracle_score(yf_sym, display=disp)
            if res:
                us100_res.append(res)
            count += 1
            self.progress.emit(int((count / total) * 100))

        results = {
            "commodities": comm_res,
            "forex": forex_res,
            "nifty200": nifty_res,
            "us100": us100_res
        }
        self.resultReady.emit(results)

class NewsWorker(QThread):
    resultReady = pyqtSignal(list, str)

    def __init__(self, symbol, display):
        super().__init__()
        self.symbol = symbol
        self.display = display

    def run(self):
        items = []
        try:
            ticker = yf.Ticker(self.symbol)
            raw = ticker.news or []
            if isinstance(raw, list):
                items = raw
        except Exception:
            items = []
        self.resultReady.emit(items, self.display)

class OutlookWorker(QThread):
    resultReady = pyqtSignal(object, str)

    def __init__(self, symbol, display, period="1y", interval="1d"):
        super().__init__()
        self.symbol = symbol
        self.display = display
        self.period = period
        self.interval = interval

    def run(self):
        try:
            outlook = compute_7day_outlook(self.symbol, self.display, self.period, self.interval)
        except Exception:
            outlook = None
        self.resultReady.emit(outlook, self.display)

# =====================================================================
# DIALOGS & WIDGETS
# =====================================================================
class TelegramSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Telegram Configuration")
        self.resize(380, 200)
        
        layout = QFormLayout(self)
        self.token_input = QLineEdit()
        self.token_input.setText(TELEGRAM_CONFIG.get("token", ""))
        self.token_input.setPlaceholderText("Enter Bot Token...")
        
        self.chat_input = QLineEdit()
        self.chat_input.setText(TELEGRAM_CONFIG.get("chat_id", ""))
        self.chat_input.setPlaceholderText("Enter Chat ID...")
        
        layout.addRow("Bot Token", self.token_input)
        layout.addRow("Chat ID", self.chat_input)
        
        btn_test = QPushButton("Send Test Message")
        btn_test.setStyleSheet(f"background-color: {COLOR_PANEL_BG}; color: {COLOR_GREEN}; border: 1px solid {COLOR_GREEN};")
        btn_test.clicked.connect(self.send_test_alert)
        layout.addRow(btn_test)
        
        btn_save = QPushButton("Save Settings")
        btn_save.clicked.connect(self.save_settings)
        layout.addRow(btn_save)

    def send_test_alert(self):
        TELEGRAM_CONFIG["token"] = self.token_input.text().strip()
        TELEGRAM_CONFIG["chat_id"] = self.chat_input.text().strip()
        
        success, msg = send_telegram_alert("🟢 *QuantFX Terminal Test Alert*\nConnection successfully established!")
        if success:
            QMessageBox.information(self, "Success", "Test message sent to Telegram successfully!")
        else:
            QMessageBox.critical(self, "Error", f"Failed to send test message:\n{msg}")

    def save_settings(self):
        TELEGRAM_CONFIG["token"] = self.token_input.text().strip()
        TELEGRAM_CONFIG["chat_id"] = self.chat_input.text().strip()
        QMessageBox.information(self, "Saved", "Telegram settings successfully updated.")
        self.accept()

class SearchDialog(QDialog):
    def __init__(self, table_widget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search")
        self.resize(300, 100)
        self.table = table_widget
        layout = QVBoxLayout(self)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter symbol...")
        self.search_input.textChanged.connect(self.filter_table)
        layout.addWidget(self.search_input)

    def filter_table(self, text):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                match = text.lower() in item.text().lower()
                self.table.setRowHidden(row, not match)

class ImageBackgroundWidget(QWidget):
    def __init__(self, image_path=None, parent=None):
        super().__init__(parent)
        self.image_path = image_path

# =====================================================================
# MAIN WINDOW
# =====================================================================
class QuantFXTerminal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QuantFX – ATR Renko & Macro Smart Money Structure")
        self.resize(1600, 900)

        self.current_symbol = "GC=F"
        self.current_display = "GOLD"
        self.current_interval = "1d"
        self.current_period = "1y"
        self.renko_len = 0
        self.ha_len = 0
        self.is_panning = False
        self.pan_start_x = None
        self.pan_source_axes = None
        self.is_syncing_x = False
        self.renko_df_cache = pd.DataFrame()
        self.ha_df_cache = pd.DataFrame()
        self.active_workers = []

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLOR_BG_DARK};
            }}
            QWidget {{
                background-color: {COLOR_BG_DARK};
                color: {COLOR_TEXT_MAIN};
                font-family: Segoe UI, sans-serif;
                font-size: 11px;
            }}
            QPushButton {{
                background-color: #1E222D;
                color: {COLOR_TEXT_MAIN};
                border: 1px solid {COLOR_BORDER};
                padding: 5px 12px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #2A2F3A;
            }}
            QTabWidget::pane {{
                border: 1px solid {COLOR_BORDER};
                background-color: {COLOR_PANEL_BG};
            }}
            QTableWidget {{
                background-color: rgba(17, 21, 28, 0.9);
                color: {COLOR_TEXT_MAIN};
                gridline-color: {COLOR_BORDER};
                font-size: 11px;
                border: none;
                selection-background-color: rgba(42, 47, 58, 0.9);
            }}
            QHeaderView::section {{
                background-color: rgba(30, 34, 45, 0.95);
                color: {COLOR_TEXT_MUTED};
                font-weight: 600;
                padding: 6px;
                border: 1px solid {COLOR_BORDER};
            }}
            QTextBrowser {{
                background-color: rgba(11, 15, 20, 0.95);
                color: #00FFCC;
                border: 1px solid {COLOR_BORDER};
                font-size: 11px;
            }}
            QProgressBar {{
                background-color: rgba(11, 15, 20, 0.8);
                height: 4px;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00FF66, stop:0.5 #00CCFF, stop:1 #FF33CC);
            }}
        """)

        central = ImageBackgroundWidget(BG_IMAGE_PATH)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        header = QHBoxLayout()
        title = QLabel("QuantFX")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #FFFFFF; letter-spacing: 1px;"
        )
        header.addWidget(title)
        header.addStretch()

        btn_telegram = QPushButton("Telegram")
        btn_telegram.clicked.connect(self.open_telegram_dialog)
        header.addWidget(btn_telegram)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.start_scan)
        header.addWidget(btn_refresh)

        layout.addLayout(header)

        self.pbar = QProgressBar()
        layout.addWidget(self.pbar)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tabs = QTabWidget()

        comm_tab_widget = QWidget()
        comm_tab_layout = QVBoxLayout(comm_tab_widget)
        comm_tab_layout.setContentsMargins(4, 4, 4, 4)

        lbl_comm_header = QLabel("COMMODITIES")
        lbl_comm_header.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {COLOR_TEXT_MUTED}; margin-bottom: 2px;"
        )
        comm_tab_layout.addWidget(lbl_comm_header)

        self.comm = self.make_table()
        comm_tab_layout.addWidget(self.comm)

        lbl_forex_header = QLabel("MAJOR FOREX PAIRS")
        lbl_forex_header.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {COLOR_TEXT_MUTED}; margin-top: 6px; margin-bottom: 2px;"
        )
        comm_tab_layout.addWidget(lbl_forex_header)

        self.forex = self.make_table()
        comm_tab_layout.addWidget(self.forex)

        self.tabs.addTab(comm_tab_widget, "Commodities & Forex")

        self.nifty_table = self.make_table()
        self.tabs.addTab(self.nifty_table, "Nifty 200")

        self.us100_table = self.make_table()
        self.tabs.addTab(self.us100_table, "US100")

        main_splitter.addWidget(self.tabs)

        chart_widget = QWidget()
        chart_layout = QVBoxLayout(chart_widget)

        tf_layout = QHBoxLayout()
        tf_label = QLabel("Macro Timeframe:")
        tf_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-weight: bold;")
        tf_layout.addWidget(tf_label)

        self.btn_tf_15m = QPushButton("15m")
        self.btn_tf_30m = QPushButton("30m")
        self.btn_tf_1h = QPushButton("1h")
        self.btn_tf_4h = QPushButton("4h")
        self.btn_tf_1d = QPushButton("1d")
        self.btn_tf_1wk = QPushButton("1wk")

        self.tf_buttons = {
            "15m": self.btn_tf_15m,
            "30m": self.btn_tf_30m,
            "60m": self.btn_tf_1h,
            "4h": self.btn_tf_4h,
            "1d": self.btn_tf_1d,
            "1wk": self.btn_tf_1wk
        }

        self.btn_tf_15m.clicked.connect(lambda: self.set_timeframe("15m"))
        self.btn_tf_30m.clicked.connect(lambda: self.set_timeframe("30m"))
        self.btn_tf_1h.clicked.connect(lambda: self.set_timeframe("60m"))
        self.btn_tf_4h.clicked.connect(lambda: self.set_timeframe("4h"))
        self.btn_tf_1d.clicked.connect(lambda: self.set_timeframe("1d"))
        self.btn_tf_1wk.clicked.connect(lambda: self.set_timeframe("1wk"))

        for b in [self.btn_tf_15m, self.btn_tf_30m, self.btn_tf_1h, self.btn_tf_4h, self.btn_tf_1d, self.btn_tf_1wk]:
            tf_layout.addWidget(b)

        tf_layout.addStretch()
        self.btn_zoom_in = QPushButton("Zoom In (+)")
        self.btn_zoom_out = QPushButton("Zoom Out (-)")
        self.btn_zoom_in.clicked.connect(lambda: self.adjust_zoom(0.8))
        self.btn_zoom_out.clicked.connect(lambda: self.adjust_zoom(1.25))
        tf_layout.addWidget(self.btn_zoom_in)
        tf_layout.addWidget(self.btn_zoom_out)

        chart_layout.addLayout(tf_layout)

        ema_param_layout = QHBoxLayout()
        lbl_fast = QLabel("EMA Fast:")
        self.spin_fast = QSpinBox()
        self.spin_fast.setRange(1, 200)
        self.spin_fast.setValue(21)
        self.spin_fast.valueChanged.connect(self.plot_atr_renko_chart)

        lbl_slow = QLabel("EMA Slow:")
        self.spin_slow = QSpinBox()
        self.spin_slow.setRange(1, 200)
        self.spin_slow.setValue(50)
        self.spin_slow.valueChanged.connect(self.plot_atr_renko_chart)

        ema_param_layout.addWidget(lbl_fast)
        ema_param_layout.addWidget(self.spin_fast)
        ema_param_layout.addWidget(lbl_slow)
        ema_param_layout.addWidget(self.spin_slow)
        ema_param_layout.addStretch()
        chart_layout.addLayout(ema_param_layout)

        self.chart_title = QLabel("ATR Renko × 3 + Macro EMA Cross")
        self.chart_title.setStyleSheet(
            f"font-size: 12px; color: {COLOR_TEXT_MUTED}; font-weight: bold;"
        )
        chart_layout.addWidget(self.chart_title)

        plt.style.use("dark_background")

        self.fig_ha, self.ax_ha = plt.subplots(figsize=(7, 3.6))
        self.fig_ha.patch.set_facecolor(COLOR_BG_DARK)
        self.ax_ha.set_facecolor(COLOR_BG_DARK)
        self.canvas_ha = FigureCanvas(self.fig_ha)
        chart_layout.addWidget(self.canvas_ha, 2)

        self.fig_main, self.ax = plt.subplots(figsize=(7, 3.6))
        self.fig_main.patch.set_facecolor(COLOR_BG_DARK)
        self.ax.set_facecolor(COLOR_BG_DARK)
        self.canvas_main = FigureCanvas(self.fig_main)
        chart_layout.addWidget(self.canvas_main, 2)

        self.fig_macd, self.ax_macd = plt.subplots(figsize=(7, 1.8))
        self.fig_macd.patch.set_facecolor(COLOR_BG_DARK)
        self.ax_macd.set_facecolor(COLOR_BG_DARK)
        self.canvas_macd = FigureCanvas(self.fig_macd)
        chart_layout.addWidget(self.canvas_macd, 1)

        self.fig_rsi, self.ax_rsi = plt.subplots(figsize=(7, 1.8))
        self.fig_rsi.patch.set_facecolor(COLOR_BG_DARK)
        self.ax_rsi.set_facecolor(COLOR_BG_DARK)
        self.canvas_rsi = FigureCanvas(self.fig_rsi)
        chart_layout.addWidget(self.canvas_rsi, 1)

        for canvas in (self.canvas_ha, self.canvas_main, self.canvas_macd, self.canvas_rsi):
            canvas.mpl_connect("scroll_event", self.on_scroll_zoom)
            canvas.mpl_connect("button_press_event", self.on_mouse_press)
            canvas.mpl_connect("motion_notify_event", self.on_mouse_drag)
            canvas.mpl_connect("button_release_event", self.on_mouse_release)

        main_splitter.addWidget(chart_widget)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        outlook_widget = QWidget()
        outlook_widget.setStyleSheet(
            f"background-color: {COLOR_PANEL_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 4px;"
        )
        outlook_layout = QVBoxLayout(outlook_widget)
        outlook_layout.setContentsMargins(10, 6, 10, 6)

        self.outlook_title = QLabel("OUTLOOK")
        self.outlook_title.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #00FFCC; margin-bottom: 2px;"
        )
        outlook_layout.addWidget(self.outlook_title)

        self.outlook_box = QTextBrowser()
        self.outlook_box.setOpenExternalLinks(False)
        self.outlook_box.setFixedHeight(190)
        self.outlook_box.setStyleSheet("border: none; background-color: transparent;")
        self.outlook_box.setHtml(
            f"<p style='color:{COLOR_TEXT_MUTED};'>Loading outlook…</p>"
        )
        outlook_layout.addWidget(self.outlook_box)

        outlook_widget.setMaximumHeight(230)
        right_layout.addWidget(outlook_widget, 0)

        news_widget = QWidget()
        news_layout = QVBoxLayout(news_widget)
        self.news_title = QLabel("LIVE NEWS")
        self.news_title.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #00FFCC;"
        )
        news_layout.addWidget(self.news_title)

        self.news_box = QTextBrowser()
        self.news_box.setOpenExternalLinks(True)
        self.news_box.setHtml(
            f"<p style='color:{COLOR_TEXT_MUTED};'>Loading news…</p>"
        )
        news_layout.addWidget(self.news_box)

        right_layout.addWidget(news_widget, 1)

        main_splitter.addWidget(right_panel)

        main_splitter.setSizes([500, 750, 350])
        layout.addWidget(main_splitter)

        self.status = QLabel("Ready")
        self.status.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        layout.addWidget(self.status)

        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_search.activated.connect(self.open_search_dialog)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(600000)
        self.refresh_timer.timeout.connect(self.start_scan)
        self.refresh_timer.start()

        QTimer.singleShot(100, self.start_scan)

    def set_timeframe(self, interval):
        self.current_interval = interval
        if interval == "15m":
            self.current_period = "10d"
        elif interval == "30m":
            self.current_period = "20d"
        elif interval == "60m":
            self.current_period = "60d"
        elif interval == "4h":
            self.current_period = "180d"
        elif interval == "1d":
            self.current_period = "1y"
        elif interval == "1wk":
            self.current_period = "5y"
        
        for tf_key, btn in self.tf_buttons.items():
            if tf_key == self.current_interval:
                btn.setStyleSheet(f"background-color: {COLOR_GREEN}; color: #000000; border: 1px solid {COLOR_GREEN}; font-weight: bold;")
            else:
                btn.setStyleSheet("")

        self.plot_atr_renko_chart()
        self.refresh_outlook()

    def make_table(self):
        t = QTableWidget()
        t.setColumnCount(12)
        t.setHorizontalHeaderLabels([
            "Symbol", "Price", "Change % ⇅", "Day High", "Day Low",
            "Call", "Structure", "Score ⇅", "SL", "TP1", "TP1% ⇅", "TP2"
        ])
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.verticalHeader().setVisible(False)
        t.cellClicked.connect(lambda r, c, tab=t: self.cell_click(tab, r, c))
        t.setSortingEnabled(True)
        return t

    def fill_table(self, table, rows):
        table.setRowCount(0)
        table.setSortingEnabled(False)
        for r_idx, row in enumerate(rows):
            table.insertRow(r_idx)

            sym_item = QTableWidgetItem(row["Ticker"])
            sym_item.setData(Qt.ItemDataRole.UserRole, row)
            table.setItem(r_idx, 0, sym_item)

            table.setItem(r_idx, 1, NumericTableWidgetItem(row["Price"]))

            chg_item = NumericTableWidgetItem(row["ChangePct"])
            raw_chg = row.get("RawChange", 0.0)
            chg_item.setForeground(QColor(COLOR_GREEN) if raw_chg >= 0 else QColor(COLOR_RED))
            table.setItem(r_idx, 2, chg_item)

            table.setItem(r_idx, 3, NumericTableWidgetItem(row["DayHigh"]))
            table.setItem(r_idx, 4, NumericTableWidgetItem(row["DayLow"]))

            call_item = QTableWidgetItem(row["Signal"])
            call_item.setForeground(QColor(COLOR_GREEN) if row["Signal"] == "BUY" else QColor(COLOR_RED))
            table.setItem(r_idx, 5, call_item)

            struct_item = QTableWidgetItem(row.get("Structure", "—"))
            struct_color_map = {
                "BOS_DEMAND": COLOR_BOS_DEMAND,
                "BOS_SUPPLY": COLOR_BOS_SUPPLY,
                "CHOCH_DEMAND": COLOR_CHOCH_DEMAND,
                "CHOCH_SUPPLY": COLOR_CHOCH_SUPPLY,
            }
            struct_type = row.get("StructureType")
            if struct_type in struct_color_map:
                struct_item.setForeground(QColor(struct_color_map[struct_type]))
            else:
                struct_item.setForeground(QColor(COLOR_TEXT_MUTED))
            table.setItem(r_idx, 6, struct_item)

            table.setItem(r_idx, 7, NumericTableWidgetItem(row["Score"]))
            table.setItem(r_idx, 8, NumericTableWidgetItem(row["SL"]))
            table.setItem(r_idx, 9, NumericTableWidgetItem(row["TP1"]))
            table.setItem(r_idx, 10, NumericTableWidgetItem(row["TP1_PCT"]))
            table.setItem(r_idx, 11, NumericTableWidgetItem(row["TP2"]))

        table.setSortingEnabled(True)

    def cell_click(self, table, row, col):
        item = table.item(row, 0)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and isinstance(data, dict):
                self.current_symbol = data["RawSymbol"]
                self.current_display = item.text()
                self.plot_atr_renko_chart()
                self.refresh_news()
                self.refresh_outlook()

    def open_search_dialog(self):
        SearchDialog(self.comm, self).exec()

    def open_telegram_dialog(self):
        TelegramSettingsDialog(self).exec()

    def _launch_worker(self, worker):
        self.active_workers.append(worker)

        def _cleanup(*_args, w=worker):
            if w in self.active_workers:
                self.active_workers.remove(w)
            w.deleteLater()

        worker.finished.connect(_cleanup)
        worker.start()
        return worker

    def start_scan(self):
        self.status.setText("Scanning market data...")
        self.pbar.setValue(0)
        self.worker = ScannerWorker()
        self.worker.progress.connect(self.pbar.setValue)
        self.worker.resultReady.connect(self.populate_tables_and_tabs)
        self._launch_worker(self.worker)

    def send_filtered_trading_alerts(self, scan_results):
        commodities = scan_results.get("commodities", [])
        us100 = scan_results.get("us100", [])
        nifty200 = scan_results.get("nifty200", [])

        def filter_and_sort(items, top_n=None):
            valid = []
            for item in items:
                try:
                    score = float(item["Score"].replace("%", ""))
                    tp1_pct = float(item["TP1_PCT"].replace("%", ""))
                    if score >= 50.0 and tp1_pct >= 5.0:
                        valid.append((score, tp1_pct, item))
                except (ValueError, KeyError):
                    continue
            valid.sort(key=lambda x: (x[0], x[1]), reverse=True)
            entries = [entry[2] for entry in valid]
            return entries[:top_n] if top_n else entries

        top_us100 = filter_and_sort(us100, top_n=5)
        top_nifty = filter_and_sort(nifty200, top_n=5)

        msg_lines = [
            "🚨 *QUANTFX HIGH-PROBABILITY ALERTS* 🚨",
            "_(Score ≥ 50%, TP1% ≥ 5%)_\n"
        ]

        msg_lines.append("🪙 *Commodities Status:*")
        if commodities:
            for c in commodities:
                msg_lines.append(f"• *{c['Ticker']}*: {c['Signal']} | Structure: {c.get('Structure', '—')} | Price: {c['Price']} ({c['ChangePct']}) | Score: {c['Score']} | TP1: {c['TP1_PCT']}")
        else:
            msg_lines.append("• No commodity data available.")

        msg_lines.append("\n🇺🇸 *US100 Top 5 Stocks:*")
        if top_us100:
            for s in top_us100:
                msg_lines.append(f"• *{s['Ticker']}*: {s['Signal']} | Structure: {s.get('Structure', '—')} | Price: {s['Price']} | Score: {s['Score']} | TP1: {s['TP1_PCT']}")
        else:
            msg_lines.append("• No qualifying US100 stocks found.")

        msg_lines.append("\n🇮🇳 *Nifty 200 Top 5 Stocks:*")
        if top_nifty:
            for n in top_nifty:
                msg_lines.append(f"• *{n['Ticker']}*: {n['Signal']} | Structure: {n.get('Structure', '—')} | Price: {n['Price']} | Score: {n['Score']} | TP1: {n['TP1_PCT']}")
        else:
            msg_lines.append("• No qualifying Nifty 200 stocks found.")

        final_message = "\n".join(msg_lines)
        send_telegram_alert(final_message)

    def populate_tables_and_tabs(self, data):
        self.fill_table(self.comm, data.get("commodities", []))
        self.fill_table(self.forex, data.get("forex", []))
        self.fill_table(self.nifty_table, data.get("nifty200", []))
        self.fill_table(self.us100_table, data.get("us100", []))

        self.status.setText("Scan complete.")
        self.set_timeframe("1d")
        self.refresh_news()
        self.refresh_outlook()
        
        if TELEGRAM_CONFIG.get("token") and TELEGRAM_CONFIG.get("chat_id"):
            self.send_filtered_trading_alerts(data)

    def refresh_news(self):
        self.news_title.setText(f"LIVE NEWS — {self.current_display}")
        self.news_box.setHtml(f"<p style='color:{COLOR_TEXT_MUTED};'>Loading news for {self.current_display}…</p>")
        self.news_worker = NewsWorker(self.current_symbol, self.current_display)
        self.news_worker.resultReady.connect(self.populate_news)
        self._launch_worker(self.news_worker)

    def populate_news(self, news_items, display):
        if display != self.current_display:
            return

        self.news_title.setText(f"LIVE NEWS — {display}")

        if not news_items:
            self.news_box.setHtml(f"<p style='color:{COLOR_TEXT_MUTED};'>No recent news found for {display}.</p>")
            return

        parts = []
        for item in news_items[:10]:
            title, publisher, link, ts_display = self._extract_news_fields(item)
            safe_title = (title or "Untitled").replace("<", "&lt;").replace(">", "&gt;")
            headline_html = f'<a href="{link}" style="color:{COLOR_TEXT_MAIN}; text-decoration:none;">{safe_title}</a>' if link else safe_title
            meta_bits = [b for b in (publisher, ts_display) if b]
            meta_html = " · ".join(meta_bits)

            parts.append(
                f"<p style='margin:0 0 2px 0; font-weight:bold; font-size:12px;'>{headline_html}</p>"
                f"<p style='margin:0 0 6px 0; color:{COLOR_TEXT_MUTED}; font-size:10px;'>{meta_html}</p>"
                f"<hr style='border-color:{COLOR_BORDER}; margin:6px 0;'>"
            )

        self.news_box.setHtml("".join(parts))

    def _extract_news_fields(self, item):
        content = item.get("content") if isinstance(item.get("content"), dict) else {}
        title = content.get("title") or item.get("title") or "Untitled"

        publisher = None
        provider = content.get("provider")
        if isinstance(provider, dict):
            publisher = provider.get("displayName")
        publisher = publisher or item.get("publisher")

        link = None
        canonical = content.get("canonicalUrl")
        if isinstance(canonical, dict):
            link = canonical.get("url")
        link = link or item.get("link") or content.get("link")

        ts_display = ""
        pub_time = item.get("providerPublishTime")
        pub_date_str = content.get("pubDate")
        try:
            if pub_time:
                ts_display = datetime.fromtimestamp(pub_time).strftime("%d %b %H:%M")
            elif pub_date_str:
                ts_display = str(pub_date_str).replace("T", " ")[:16]
        except Exception:
            ts_display = ""

        return title, publisher, link, ts_display

    def refresh_outlook(self):
        self.outlook_title.setText(f"OUTLOOK — {self.current_display} ({self.current_interval})")
        self.outlook_box.setHtml(f"<p style='color:{COLOR_TEXT_MUTED};'>Computing outlook for {self.current_display}…</p>")
        self.outlook_worker = OutlookWorker(self.current_symbol, self.current_display, self.current_period, self.current_interval)
        self.outlook_worker.resultReady.connect(self.populate_outlook)
        self._launch_worker(self.outlook_worker)

    def populate_outlook(self, outlook, display):
        if display != self.current_display:
            return

        self.outlook_title.setText(f"OUTLOOK — {display} ({self.current_interval})")

        if not outlook:
            self.outlook_box.setHtml(f"<p style='color:{COLOR_TEXT_MUTED};'>Not enough macro history to project {display}.</p>")
            return

        bias_score = outlook["bias_score"]
        conditions_met = abs(bias_score) >= 2.0

        dir_color = COLOR_GREEN if outlook["direction"] == "Bullish" else (COLOR_RED if outlook["direction"] == "Bearish" else COLOR_TEXT_MUTED)

        status_button = f"""
            <span style='background-color: {COLOR_GREEN if conditions_met else COLOR_RED}; color: {'#000000' if conditions_met else '#FFFFFF'}; padding: 2px 8px; 
            border-radius: 4px; font-weight: bold; font-size: 10px;'>{'🟢 CONDITIONS MET' if conditions_met else '🔴 CONDITIONS NOT MET'}</span>
        """

        reasons_html = "".join(f"<li style='margin-bottom:2px;'>{r}</li>" for r in outlook["reasons"])

        struct_badge = ""
        structure_event = outlook.get("structure_event")
        if structure_event:
            struct_color_map = {
                "BOS_DEMAND": COLOR_BOS_DEMAND,
                "BOS_SUPPLY": COLOR_BOS_SUPPLY,
                "CHOCH_DEMAND": COLOR_CHOCH_DEMAND,
                "CHOCH_SUPPLY": COLOR_CHOCH_SUPPLY,
            }
            s_color = struct_color_map.get(structure_event["type"], COLOR_TEXT_MUTED)
            bars_ago = structure_event["bars_ago"]
            recency = "latest brick" if bars_ago == 0 else f"{bars_ago} bricks ago"
            struct_badge = f"""
                <span style='background-color:#1E222D; color:{s_color}; border: 1px solid {s_color}; padding:2px 8px;
                border-radius:4px; font-weight:bold; font-size:10px;'>{structure_event['label']}</span>
                <span style='color:{COLOR_TEXT_MUTED}; font-size:10px;'>
                    &nbsp;@ ${structure_event['level']:,.2f} ({recency})
                </span>
            """

        html = f"""
        <p style='margin:0 0 4px 0;'>
            <span style='font-weight:bold; color:{dir_color}; font-size:13px;'>{outlook['direction']}</span>
            &nbsp;&nbsp;{status_button}
            <span style='color:{COLOR_TEXT_MUTED};'>
                &nbsp;— projected macro range ${outlook['range_low']:,.2f} – ${outlook['range_high']:,.2f}
                (last: ${outlook['last_close']:,.2f})
            </span>
        </p>
        <p style='margin:0 0 4px 0;'>{struct_badge}</p>
        <ul style='margin:0 0 4px 18px; padding:0; color:{COLOR_TEXT_MAIN}; font-size:11px;'>
            {reasons_html}
        </ul>
        """
        self.outlook_box.setHtml(html)

    def plot_atr_renko_chart(self):
        df = fetch_live_ohlc(self.current_symbol, self.current_period, self.current_interval)
        if df.empty:
            self.chart_title.setText(f"No data for {self.current_display}")
            return

        ema_fast = self.spin_fast.value()
        ema_slow = self.spin_slow.value()

        renko_df, brick_size = build_atr_renko_df(
            df, atr_period=21, atr_multiplier=3.0,
            ema_fast=ema_fast, ema_slow=ema_slow
        )
        self.renko_df_cache = renko_df

        self.ax_ha.clear()
        self.ax.clear()
        self.ax_macd.clear()
        self.ax_rsi.clear()

        self.ax_ha.set_facecolor(COLOR_BG_DARK)
        self.ax.set_facecolor(COLOR_BG_DARK)
        self.ax_macd.set_facecolor(COLOR_BG_DARK)
        self.ax_rsi.set_facecolor(COLOR_BG_DARK)

        if renko_df.empty:
            self.chart_title.setText(f"No ATR Renko bricks for {self.current_display}")
            self.canvas_ha.draw_idle()
            self.canvas_main.draw_idle()
            self.canvas_macd.draw_idle()
            self.canvas_rsi.draw_idle()
            return

        ha_df = compute_heikin_ashi(renko_df)
        ha_df["EMA_FAST"] = ha_df["Close"].ewm(span=ema_fast, adjust=False).mean()
        ha_df["EMA_SLOW"] = ha_df["Close"].ewm(span=ema_slow, adjust=False).mean()

        ha_signals = []
        for i in range(len(ha_df)):
            if i == 0:
                ha_signals.append("HOLD")
                continue
            f_now, s_now = ha_df.loc[i, "EMA_FAST"], ha_df.loc[i, "EMA_SLOW"]
            f_prev, s_prev = ha_df.loc[i-1, "EMA_FAST"], ha_df.loc[i-1, "EMA_SLOW"]
            if f_now > s_now and f_prev <= s_prev:
                ha_signals.append("BUY")
            elif f_now < s_now and f_prev >= s_prev:
                ha_signals.append("SELL")
            else:
                ha_signals.append("HOLD")
        ha_df["Signal"] = ha_signals

        self.ha_df_cache = ha_df
        self.ha_len = len(ha_df)
        self.renko_len = len(renko_df)

        x_vals = np.arange(len(renko_df))
        dates = renko_df["Date"]

        # ==================== HEIKIN ASHI CHART ====================
        for i in range(len(ha_df)):
            o, c, h, l = ha_df["Open"].iloc[i], ha_df["Close"].iloc[i], ha_df["High"].iloc[i], ha_df["Low"].iloc[i]
            x = x_vals[i]
            candle_color = COLOR_BULL if c >= o else COLOR_BEAR

            self.ax_ha.plot([x, x], [l, h], color=candle_color, linewidth=1.2, zorder=2)
            rect = patches.Rectangle(
                (x - 0.4, min(o, c)), 0.8,
                max(abs(c - o), (h - l) * 0.02 if h != l else 0.0001),
                facecolor=candle_color, edgecolor=candle_color, linewidth=0.8, zorder=3
            )
            self.ax_ha.add_patch(rect)

        self.ax_ha.plot(x_vals, ha_df["EMA_FAST"], color=COLOR_MA9, linewidth=1.5, label=f"EMA {ema_fast}", zorder=4)
        self.ax_ha.plot(x_vals, ha_df["EMA_SLOW"], color=COLOR_MA20, linewidth=1.5, label=f"EMA {ema_slow}", zorder=4)

        for i in range(len(ha_df)):
            sig = ha_df["Signal"].iloc[i]
            if sig == "HOLD":
                continue
            x, price = x_vals[i], ha_df["Close"].iloc[i]
            if sig == "BUY":
                self.ax_ha.text(
                    x, price - brick_size * 0.4, "BUY",
                    color="#FFFFFF", fontsize=7.5, ha="center", va="top",
                    bbox=dict(boxstyle="round,pad=0.3", fc="#1E222D", ec=COLOR_GREEN, lw=1.0),
                    zorder=5
                )
            elif sig == "SELL":
                self.ax_ha.text(
                    x, price + brick_size * 0.4, "SELL",
                    color="#FFFFFF", fontsize=7.5, ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.3", fc="#1E222D", ec=COLOR_RED, lw=1.0),
                    zorder=5
                )

        # ==================== RENKO CHART ====================
        self.chart_title.setText(f"{self.current_display} ATR Renko × 3 + Macro EMA Cross")

        for i, row in renko_df.iterrows():
            x = x_vals[i]
            o, c = row["Open"], row["Close"]
            brick_color = COLOR_BULL if row["Type"] == "up" else COLOR_BEAR

            rect = patches.Rectangle(
                (x - 0.4, min(o, c)), 0.8, abs(c - o),
                facecolor=brick_color, edgecolor="#1E222D", linewidth=0.8, zorder=5
            )
            self.ax.add_patch(rect)

        self.ax.plot(x_vals, renko_df["EMA_FAST"], color=COLOR_MA9, linewidth=1.5, label=f"EMA {ema_fast}")
        self.ax.plot(x_vals, renko_df["EMA_SLOW"], color=COLOR_MA20, linewidth=1.5, label=f"EMA {ema_slow}")

        for i in range(1, len(renko_df)):
            sig = renko_df["Signal"].iloc[i]
            if sig == "HOLD":
                continue
            x, price = x_vals[i], renko_df["Close"].iloc[i]
            if sig == "BUY":
                self.ax.text(
                    x, price - brick_size * 0.4, "BUY",
                    color="#FFFFFF", fontsize=7.5, ha="center", va="top",
                    bbox=dict(boxstyle="round,pad=0.3", fc="#1E222D", ec=COLOR_GREEN, lw=1.0),
                    zorder=6
                )
            elif sig == "SELL":
                self.ax.text(
                    x, price + brick_size * 0.4, "SELL",
                    color="#FFFFFF", fontsize=7.5, ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.3", fc="#1E222D", ec=COLOR_RED, lw=1.0),
                    zorder=6
                )

        # --- ALIGNED SWING MARKERS & BOS / CHoCH OVERLAYS ACROSS ALL CHARTS ---
        if "SwingHigh" in renko_df.columns:
            swing_high_idx = renko_df.index[renko_df["SwingHigh"]].tolist()
            swing_low_idx = renko_df.index[renko_df["SwingLow"]].tolist()
            
            if swing_high_idx:
                self.ax.scatter(
                    [x_vals[i] for i in swing_high_idx], [renko_df["High"].iloc[i] for i in swing_high_idx],
                    marker="v", s=26, color=COLOR_SWING_MARKER, zorder=4, alpha=0.35, edgecolors=COLOR_BG_DARK, linewidths=0.5
                )
                self.ax_ha.scatter(
                    [x_vals[i] for i in swing_high_idx], [ha_df["High"].iloc[i] for i in swing_high_idx],
                    marker="v", s=26, color=COLOR_SWING_MARKER, zorder=4, alpha=0.35, edgecolors=COLOR_BG_DARK, linewidths=0.5
                )

            if swing_low_idx:
                self.ax.scatter(
                    [x_vals[i] for i in swing_low_idx], [renko_df["Low"].iloc[i] for i in swing_low_idx],
                    marker="^", s=26, color=COLOR_SWING_MARKER, zorder=4, alpha=0.35, edgecolors=COLOR_BG_DARK, linewidths=0.5
                )
                self.ax_ha.scatter(
                    [x_vals[i] for i in swing_low_idx], [ha_df["Low"].iloc[i] for i in swing_low_idx],
                    marker="^", s=26, color=COLOR_SWING_MARKER, zorder=4, alpha=0.35, edgecolors=COLOR_BG_DARK, linewidths=0.5
                )

        if "Structure" in renko_df.columns:
            struct_style = {
                "BOS_DEMAND": (COLOR_BOS_DEMAND, "B-S"),
                "BOS_SUPPLY": (COLOR_BOS_SUPPLY, "B-D"),
                "CHOCH_DEMAND": (COLOR_CHOCH_DEMAND, "CH-S"),
                "CHOCH_SUPPLY": (COLOR_CHOCH_SUPPLY, "CH-D"),
            }
            has_origin = "StructureOriginIdx" in renko_df.columns
            
            for i in range(len(renko_df)):
                s_type = renko_df["Structure"].iloc[i]
                if s_type not in ["BOS_DEMAND", "BOS_SUPPLY", "CHOCH_DEMAND", "CHOCH_SUPPLY"]:
                    continue
                
                color, base_label = struct_style.get(s_type, (COLOR_TEXT_MUTED, s_type))
                s_level = renko_df["StructureLevel"].iloc[i]
                x = x_vals[i]

                origin_idx = renko_df["StructureOriginIdx"].iloc[i] if has_origin else None
                span_start = x_vals[int(origin_idx)] if pd.notna(origin_idx) else max(x - 6, x_vals[0])
                
                self.ax.plot(
                    [span_start, x], [s_level, s_level],
                    color=color, linewidth=1.1, linestyle="--", alpha=0.45, zorder=3
                )
                self.ax_ha.plot(
                    [span_start, x], [s_level, s_level],
                    color=color, linewidth=1.1, linestyle="--", alpha=0.45, zorder=3
                )

                label = base_label
                is_bullish = s_type in ("BOS_DEMAND", "CHOCH_DEMAND")
                
                y_text_renko = s_level - brick_size * 0.6 if is_bullish else s_level + brick_size * 0.6
                self.ax.text(
                    x, y_text_renko, label,
                    color="#FFFFFF", fontsize=7.2, fontweight="bold", ha="center",
                    va="top" if is_bullish else "bottom",
                    bbox=dict(boxstyle="round,pad=0.35", fc="#1E222D", ec=color, lw=1.2),
                    zorder=6
                )

                y_text_ha = s_level - brick_size * 0.6 if is_bullish else s_level + brick_size * 0.6
                self.ax_ha.text(
                    x, y_text_ha, label,
                    color="#FFFFFF", fontsize=7.2, fontweight="bold", ha="center",
                    va="top" if is_bullish else "bottom",
                    bbox=dict(boxstyle="round,pad=0.35", fc="#1E222D", ec=color, lw=1.2),
                    zorder=6
                )

                for target_ax in (self.ax_ha, self.ax, self.ax_macd, self.ax_rsi):
                    target_ax.axvline(
                        x=x, color=color, linestyle=":", alpha=0.4, linewidth=1.1, zorder=1
                    )

        self.ax_ha.set_title(f"{self.current_display} Heikin Ashi", fontsize=10, color=COLOR_TEXT_MUTED, loc="left")
        self.ax_ha.yaxis.tick_right()
        self.ax_ha.yaxis.set_label_position("right")
        self.ax_ha.legend(loc="upper left", fontsize=8)
        self.ax_ha.grid(alpha=0.12, color="#2A2F3A")
        self.ax_ha.set_xlim(-1, len(renko_df) + 1)
        plt.setp(self.ax_ha.get_xticklabels(), visible=False)

        self.ax.yaxis.tick_right()
        self.ax.yaxis.set_label_position("right")
        self.ax.set_ylabel("Macro Price")
        self.ax.legend(loc="upper left", fontsize=8)
        self.ax.grid(alpha=0.12, color="#2A2F3A")
        self.ax.set_xlim(-1, len(renko_df) + 1)
        plt.setp(self.ax.get_xticklabels(), visible=False)

        # ==================== MACD CHART WITH LINES ONLY (HISTOGRAM REMOVED) ====================
        self.ax_macd.plot(x_vals, renko_df["MACD"], color=COLOR_MACD_LINE, linewidth=1.2, label="MACD Line", zorder=3)
        self.ax_macd.plot(x_vals, renko_df["MACD_Signal"], color=COLOR_SIGNAL_LINE, linewidth=1.2, label="Signal Line", zorder=3)
        self.ax_macd.axhline(0, color=COLOR_ZERO_LINE, linewidth=0.8, zorder=1)

        for i in range(len(renko_df)):
            div_sig = renko_df["Div_Signal"].iloc[i]
            if div_sig == "BUY":
                self.ax_macd.text(
                    x_vals[i], renko_df["MACD"].iloc[i] - 0.2, "BUY",
                    color="#FFFFFF", fontsize=7.5, ha="center", va="top",
                    bbox=dict(boxstyle="round,pad=0.3", fc="#1E222D", ec=COLOR_GREEN, lw=1.0),
                    zorder=5
                )
            elif div_sig == "SELL":
                self.ax_macd.text(
                    x_vals[i], renko_df["MACD"].iloc[i] + 0.2, "SELL",
                    color="#FFFFFF", fontsize=7.5, ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.3", fc="#1E222D", ec=COLOR_RED, lw=1.0),
                    zorder=5
                )

        self.ax_macd.set_title("Macro MACD Strategy", fontsize=10, color=COLOR_TEXT_MUTED, loc="left")
        self.ax_macd.yaxis.tick_right()
        self.ax_macd.yaxis.set_label_position("right")
        self.ax_macd.legend(loc="upper left", fontsize=8)
        self.ax_macd.grid(alpha=0.12, color="#2A2F3A")
        self.ax_macd.set_xlim(-1, len(renko_df) + 1)
        plt.setp(self.ax_macd.get_xticklabels(), visible=False)

        # ==================== RSI CHART ====================
        self.ax_rsi.plot(x_vals, renko_df["RSI"], color="#FFD700", linewidth=1.2, label="RSI")
        self.ax_rsi.axhline(70, color=COLOR_RED, linewidth=0.8, linestyle="--")
        self.ax_rsi.axhline(30, color=COLOR_GREEN, linewidth=0.8, linestyle="--")
        self.ax_rsi.set_ylim(0, 100)
        self.ax_rsi.yaxis.tick_right()
        self.ax_rsi.yaxis.set_label_position("right")
        self.ax_rsi.legend(loc="upper left", fontsize=8)
        self.ax_rsi.grid(alpha=0.12, color="#2A2F3A")
        self.ax_rsi.set_xlim(-1, len(renko_df) + 1)

        step = max(len(x_vals) // 8, 1)
        self.ax_rsi.set_xticks(x_vals[::step])
        # Changed date format from %d-%m-%Y to %d-%m
        self.ax_rsi.set_xticklabels(
            [pd.Timestamp(d).strftime("%d-%m") for d in dates[::step]],
            rotation=0, ha="center", fontsize=8
        )

        self.canvas_ha.draw_idle()
        self.canvas_main.draw_idle()
        self.canvas_macd.draw_idle()
        self.canvas_rsi.draw_idle()

    def adjust_zoom(self, factor):
        if self.renko_len <= 0:
            return
        xmin, xmax = self.ax.get_xlim()
        xmid = (xmin + xmax) / 2.0
        new_range = (xmax - xmin) * factor
        self.sync_x_axis_and_rescale((xmid - new_range / 2.0, xmid + new_range / 2.0), self.renko_len)

    def sync_x_axis_and_rescale(self, new_xlim, source_len):
        if self.is_syncing_x or source_len <= 0:
            return
        self.is_syncing_x = True
        try:
            frac_min = new_xlim[0] / source_len
            frac_max = new_xlim[1] / source_len

            if self.renko_len > 0:
                renko_xlim = (frac_min * self.renko_len, frac_max * self.renko_len)
                self.ax.set_xlim(renko_xlim)
                self.ax_macd.set_xlim(renko_xlim)
                self.ax_rsi.set_xlim(renko_xlim)
                self.ax_ha.set_xlim(renko_xlim)

                self.canvas_ha.draw_idle()
                self.canvas_main.draw_idle()
                self.canvas_macd.draw_idle()
                self.canvas_rsi.draw_idle()
        finally:
            self.is_syncing_x = False

    def on_scroll_zoom(self, event):
        if event.inaxes not in (self.ax_ha, self.ax, self.ax_macd, self.ax_rsi):
            return
        source_len = self.renko_len
        if source_len <= 0:
            return
        factor = 0.8 if event.button == "up" else 1.25
        xmin, xmax = event.inaxes.get_xlim()
        xmid = (xmin + xmax) / 2.0
        new_range = (xmax - xmin) * factor
        self.sync_x_axis_and_rescale((xmid - new_range / 2.0, xmid + new_range / 2.0), source_len)

    def on_mouse_press(self, event):
        if event.inaxes in (self.ax_ha, self.ax, self.ax_macd, self.ax_rsi) and event.button == 1:
            self.is_panning = True
            self.pan_start_x = event.xdata
            self.pan_source_axes = event.inaxes

    def on_mouse_drag(self, event):
        if not self.is_panning or self.pan_source_axes is None or self.pan_start_x is None:
            return
        if event.inaxes is not self.pan_source_axes or event.xdata is None:
            return
        source_len = self.renko_len
        if source_len <= 0:
            return
        dx = self.pan_start_x - event.xdata
        cur_xmin, cur_xmax = self.pan_source_axes.get_xlim()
        self.sync_x_axis_and_rescale((cur_xmin + dx, cur_xmax + dx), source_len)

    def on_mouse_release(self, event):
        self.is_panning = False
        self.pan_start_x = None
        self.pan_source_axes = None

    def closeEvent(self, event):
        for worker in list(self.active_workers):
            if worker.isRunning():
                worker.wait(3000)
        super().closeEvent(event)

# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    terminal = QuantFXTerminal()
    terminal.show()
    sys.exit(app.exec())
