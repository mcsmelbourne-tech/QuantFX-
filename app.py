import json
import os
import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

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
COLOR_MACD_LINE = "#2962FF"
COLOR_SIGNAL_LINE = "#FF6D00"
COLOR_ZERO_LINE = "#4C566A"
COLOR_BOS_DEMAND = "#26FF9A"
COLOR_BOS_SUPPLY = "#FF4F7B"
COLOR_CHOCH_DEMAND = "#00D4FF"
COLOR_CHOCH_SUPPLY = "#FF9900"

# =====================================================================
# GLOBAL DARK THEME CSS & BLINKING / TICKING ANIMATION
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
    
    /* Blinking & Ticking Keyframes for Buy/Sell Signals */
    @keyframes qfxBlinkTick {{
      0% {{ opacity: 1; transform: scale(1); filter: brightness(1); }}
      50% {{ opacity: 0.25; transform: scale(1.08); filter: brightness(1.3); }}
      100% {{ opacity: 1; transform: scale(1); filter: brightness(1); }}
    }}
    .qfx-blinking-signal {{
      animation: qfxBlinkTick 1s infinite ease-in-out !important;
    }}
    /* Font size 10 override for chart labels & text elements */
    .js-plotly-plot .plotly .gtitle,
    .js-plotly-plot .plotly .xtitle,
    .js-plotly-plot .plotly .ytitle,
    .js-plotly-plot .plotly .legendtext,
    .js-plotly-plot .plotly .xtick text,
    .js-plotly-plot .plotly .ytick text,
    .js-plotly-plot .plotly .annotation text {{
        font-size: 10px !important;
    }}
    /* Trim header whitespace without hiding content */
    .block-container, section.main > div.block-container {{
        padding-top: 1.5rem !important;
        padding-bottom: 0.8rem !important;
    }}
    div[data-testid="stVerticalBlock"] {{
        gap: 0.35rem !important;
    }}
    h2 {{
        margin-top: 0 !important;
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
        padding-top: 0 !important;
        font-size: 1.3rem !important;
        line-height: 1.4 !important;
        overflow: visible !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# =====================================================================
# TELEGRAM CONFIGURATION
# =====================================================================
TG_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".qfx_telegram_config.json"
)

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
# INDICATORS & SIGNAL GENERATORS
# =====================================================================
def compute_heikin_ashi(df, ema_fast=21, ema_slow=50, ema_mid=None):
  ha = pd.DataFrame(index=df.index)
  ha["Close"] = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4.0
  ha_open = [(df["Open"].iloc[0] + df["Close"].iloc[0]) / 2.0]
  for i in range(1, len(df)):
    ha_open.append((ha_open[i - 1] + ha["Close"].iloc[i - 1]) / 2.0)
  ha["Open"] = ha_open
  ha["High"] = pd.concat([df["High"], ha["Open"], ha["Close"]], axis=1).max(axis=1)
  ha["Low"] = pd.concat([df["High"], ha["Open"], ha["Close"]], axis=1).min(axis=1)
  ha["EMA_FAST"] = ha["Close"].ewm(span=ema_fast, adjust=False).mean()
  ha["EMA_SLOW"] = ha["Close"].ewm(span=ema_slow, adjust=False).mean()
  if ema_mid is not None:
    ha["EMA_MID"] = ha["Close"].ewm(span=ema_mid, adjust=False).mean()
  ha_signals = ["HOLD"] * len(ha)
  for i in range(1, len(ha)):
    if (
        ha["EMA_FAST"].iloc[i] > ha["EMA_SLOW"].iloc[i]
        and ha["EMA_FAST"].iloc[i - 1] <= ha["EMA_SLOW"].iloc[i - 1]
    ):
      ha_signals[i] = "BUY"
    elif (
        ha["EMA_FAST"].iloc[i] < ha["EMA_SLOW"].iloc[i]
        and ha["EMA_FAST"].iloc[i - 1] >= ha["EMA_SLOW"].iloc[i - 1]
    ):
      ha_signals[i] = "SELL"
  ha["Signal"] = ha_signals
  return ha

def detect_macd_crossovers(renko_df, cooldown=1):
  macd = renko_df["MACD"].values
  signal = renko_df["MACD_Signal"].values
  n = len(renko_df)
  macd_signals = ["HOLD"] * n
  macd_types = [None] * n
  if n < 2:
    return macd_signals, macd_types
  
  last_fired = -cooldown - 1
  for i in range(1, n):
    if not (
        np.isfinite(macd[i])
        and np.isfinite(signal[i])
        and np.isfinite(macd[i - 1])
        and np.isfinite(signal[i - 1])
    ):
      continue
    crossed_up = macd[i] > signal[i] and macd[i - 1] <= signal[i - 1]
    crossed_down = macd[i] < signal[i] and macd[i - 1] >= signal[i - 1]
    if not (crossed_up or crossed_down):
      continue
    if i - last_fired < cooldown:
      continue
    if crossed_up:
      macd_signals[i] = "BUY"
      macd_types[i] = "MACD Cross Up"
      last_fired = i
    elif crossed_down:
      macd_signals[i] = "SELL"
      macd_types[i] = "MACD Cross Down"
      last_fired = i
  return macd_signals, macd_types

def detect_rsi_signals(renko_df, min_gap=1.0, cooldown=1):
  if "RSI" not in renko_df.columns:
    return ["HOLD"] * len(renko_df), [None] * len(renko_df)
  rsi = renko_df["RSI"].values
  n = len(renko_df)
  rsi_signals = ["HOLD"] * n
  rsi_types = [None] * n
  if n < 2:
    return rsi_signals, rsi_types
  
  rsi_series = pd.Series(rsi)
  rsi_signal_line = rsi_series.ewm(span=9, adjust=False).mean().values
  
  last_fired = -cooldown - 1
  for i in range(1, n):
    if not (np.isfinite(rsi[i]) and np.isfinite(rsi_signal_line[i]) and np.isfinite(rsi[i-1]) and np.isfinite(rsi_signal_line[i-1])):
      continue
    crossed_up = rsi[i] > rsi_signal_line[i] and rsi[i-1] <= rsi_signal_line[i-1] and rsi[i] < 75
    crossed_down = rsi[i] < rsi_signal_line[i] and rsi[i-1] >= rsi_signal_line[i-1] and rsi[i] > 25
    
    if not (crossed_up or crossed_down):
      continue
    if abs(rsi[i] - rsi_signal_line[i]) < min_gap:
      continue
    if i - last_fired < cooldown:
      continue
    if crossed_up:
      rsi_signals[i] = "BUY"
      rsi_types[i] = "RSI Cross Up"
      last_fired = i
    elif crossed_down:
      rsi_signals[i] = "SELL"
      rsi_types[i] = "RSI Cross Down"
      last_fired = i
  return rsi_signals, rsi_types

def format_price(value):
  try:
    value = float(value)
  except (TypeError, ValueError):
    return str(value)
  if value != value:
    return "—"
  abs_val = abs(value)
  if abs_val == 0:
    decimals = 2
  elif abs_val >= 1000:
    decimals = 3
  elif abs_val >= 100:
    decimals = 4
  elif abs_val >= 1:
    decimals = 5
  else:
    decimals = 8
  s = f"{value:.{decimals}f}"
  if "." in s:
    s = s.rstrip("0").rstrip(".")
  return s

def detect_triple_ema_cross_signal(close_series, fast=9, mid=21, slow=50, lookback=1):
  if close_series is None or len(close_series) < slow + 2:
    return None
  ema_fast_s = close_series.ewm(span=fast, adjust=False).mean()
  ema_mid_s = close_series.ewm(span=mid, adjust=False).mean()
  ema_slow_s = close_series.ewm(span=slow, adjust=False).mean()
  n = len(close_series)
  earliest = max(n - 1 - lookback, 1)
  for i in range(n - 1, earliest - 1, -1):
    f_now, m_now, s_now = ema_fast_s.iloc[i], ema_mid_s.iloc[i], ema_slow_s.iloc[i]
    f_prev, m_prev, s_prev = ema_fast_s.iloc[i - 1], ema_mid_s.iloc[i - 1], ema_slow_s.iloc[i - 1]
    bullish_now = f_now > m_now > s_now
    bearish_now = f_now < m_now < s_now
    bullish_prev = f_prev > m_prev > s_prev
    bearish_prev = f_prev < m_prev < s_prev
    if bullish_now and not bullish_prev:
      return {
          "direction": "BUY",
          "bars_ago": n - 1 - i,
          "fast": float(f_now),
          "mid": float(m_now),
          "slow": float(s_now),
      }
    if bearish_now and not bearish_prev:
      return {
          "direction": "SELL",
          "bars_ago": n - 1 - i,
          "fast": float(f_now),
          "mid": float(m_now),
          "slow": float(s_now),
      }
  return None

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
    data = yf.download(tickers, period="5d", interval="1d", group_by="ticker", progress=False, threads=True)
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
      results.append({"symbol": sym, "display": disp, "price": last_price, "chg": chg})
    except Exception:
      continue
  results.sort(key=lambda r: r["chg"], reverse=True)
  return results[:n]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_chartink_screener(url):
  try:
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = session.get(url, headers=headers, timeout=10)
    csrf_match = re.search(r'name="csrf-token"\s+content="([^"]+)"', resp.text)
    clause_match = re.search(r'id="scan_clause"[^>]*value="([^"]*)"', resp.text)
    if not clause_match:
      clause_match = re.search(r'<textarea[^>]*id="scan_clause"[^>]*>([^<]*)</textarea>', resp.text)
    if not csrf_match or not clause_match:
      return []
    scan_clause = clause_match.group(1)
    headers["x-csrf-token"] = csrf_match.group(1)
    resp2 = session.post(
        "https://chartink.com/screener/process",
        data={"scan_clause": scan_clause},
        headers=headers,
        timeout=10,
    )
    rows = resp2.json().get("data", [])
    results = []
    for row in rows:
      code = row.get("nsecode") or row.get("bsecode") or row.get("name") or ""
      if not code:
        continue
      try:
        price = float(row.get("close", 0) or 0)
      except (TypeError, ValueError):
        price = 0.0
      try:
        chg = float(row.get("per_chg", 0) or 0)
      except (TypeError, ValueError):
        chg = 0.0
      results.append({"symbol": f"{code}.NS", "display": code, "price": price, "chg": chg})
    return results
  except Exception:
    return []

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
      window_h = high.iloc[i - lb : i + lb + 1]
      window_l = low.iloc[i - lb : i + lb + 1]
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
        pending_high is not None
        and pending_high_idx is not None
        and i > pending_high_idx
        and c > pending_high
    )
    broke_down = (
        pending_low is not None
        and pending_low_idx is not None
        and i > pending_low_idx
        and c < pending_low
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

def build_atr_renko_df(
    df,
    atr_period=21,
    atr_multiplier=3.0,
    ema_fast=21,
    ema_slow=50,
    ema_mid=None,
    macd_fast=12,
    macd_slow=26,
    macd_signal=9,
    rsi_period=14,
):
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
            "Type": "up" if direction > 0 else "down",
        })
        current_brick_val = next_val
  if not renko_rows:
    return pd.DataFrame(), brick_size
  renko_df = pd.DataFrame(renko_rows)
  renko_df.reset_index(drop=True, inplace=True)
  r_close = renko_df["Close"]
  renko_df["EMA_FAST"] = r_close.ewm(span=ema_fast, adjust=False).mean()
  renko_df["EMA_SLOW"] = r_close.ewm(span=ema_slow, adjust=False).mean()
  if ema_mid is not None:
    renko_df["EMA_MID"] = r_close.ewm(span=ema_mid, adjust=False).mean()
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
  renko_df["MACD_Hist"] = renko_df["MACD"] - renko_df["MACD_Signal"]
  delta = r_close.diff()
  gain = (delta.where(delta > 0, 0.0)).rolling(rsi_period, min_periods=1).mean()
  loss = (-delta.where(delta < 0, 0.0)).rolling(rsi_period, min_periods=1).mean()
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
        recent_types = renko_df.loc[max(0, i - 3) : i - 1, "Type"].values
        if not pullback_fired and "down" in recent_types and brick_type == "up":
          pb_sig = "BUY"
          pullback_fired = True
      elif ema_fast_now < ema_slow_now:
        if current_trend != "SELL":
          current_trend = "SELL"
          pullback_fired = False
        recent_types = renko_df.loc[max(0, i - 3) : i - 1, "Type"].values
        if not pullback_fired and "up" in recent_types and brick_type == "down":
          pb_sig = "SELL"
          pullback_fired = True
    signals.append(sig)
    pullback_signals.append(pb_sig)
  renko_df["Signal"] = signals
  renko_df["Pullback_Signal"] = pullback_signals
  confirmed_signals = []
  for i in range(len(renko_df)):
    sig = renko_df.loc[i, "Signal"]
    pb = renko_df.loc[i, "Pullback_Signal"]
    macd_v = renko_df.loc[i, "MACD"]
    macd_s = renko_df.loc[i, "MACD_Signal"]
    rsi_v = renko_df.loc[i, "RSI"] if "RSI" in renko_df.columns else np.nan
    c = "HOLD"
    if sig == "BUY":
      c = "BUY"
    elif sig == "SELL":
      c = "SELL"
    elif pb == "BUY" and pd.notna(macd_v) and pd.notna(macd_s) and macd_v > macd_s and (pd.isna(rsi_v) or rsi_v < 75):
      c = "BUY"
    elif pb == "SELL" and pd.notna(macd_v) and pd.notna(macd_s) and macd_v < macd_s and (pd.isna(rsi_v) or rsi_v > 25):
      c = "SELL"
    confirmed_signals.append(c)
  renko_df["Confirmed_Signal"] = confirmed_signals
  
  macd_sigs, macd_types = detect_macd_crossovers(renko_df)
  renko_df["Div_Signal"] = macd_sigs
  renko_df["Div_Type"] = macd_types
  rsi_sigs, rsi_types = detect_rsi_signals(renko_df)
  renko_df["RSI_Signal"] = rsi_sigs
  renko_df["RSI_Type"] = rsi_types
  struct_df = detect_market_structure(
      renko_df["High"],
      renko_df["Low"],
      renko_df["Close"],
      swing_lookback=5,
      brick_type=renko_df["Type"],
  )
  renko_df = pd.concat([renko_df.reset_index(drop=True), struct_df.reset_index(drop=True)], axis=1)
  return renko_df, brick_size

# =====================================================================
# WATCHLISTS & CONSTANTS
# =====================================================================
nifty200_raw = [
    "ABB", "ABFRL", "ACC", "ADANIENSOL", "ADANIENT", "ADANIGREEN", "ADANIPORTS",
    "ADANIPOWER", "AFFLE", "ALKEM", "AMBER", "APLAPOLLO", "APOLLOHOSP",
    "APOLLOTYRE", "ASIANPAINT", "ASTRAL", "AUBANK", "AXISBANK", "BAJAJFINSV",
    "BAJAJHFL", "BAJAJHLDNG", "BAJAJ_AUTO", "BAJFINANCE", "BANDHANBNK",
    "BANKBARODA", "BANKINDIA", "BATAINDIA", "BERGEPAINT", "BHARATFORG",
    "BHARTIARTL", "BHEL", "BIOCON", "BOSCHLTD", "BPCL", "BRITANNIA", "BSE",
    "CANBK", "CANFINHOME", "CDSL", "CEATLTD", "CGPOWER", "CHOLAFIN", "CIPLA",
    "CNX200", "COALINDIA", "COCHINSHIP", "COFORGE", "COLPAL", "CONCOR",
    "COROMANDEL", "CUMMINSIND", "DALBHARAT", "DEEPAKNTR", "DIVISLAB", "DIXON",
    "DLF", "DMART", "DRREDDY", "EICHERMOT", "ESCORTS", "EVEREADY", "EXIDEIND",
    "FACT", "FEDERALBNK", "FLUOROCHEM", "FORTIS", "GLENMARK", "GODREJCP",
    "GODREJPROP", "GOLDBEES", "GRASIM", "HAL", "HAVELLS", "HCLTECH", "HDFCAMC",
    "HDFCBANK", "HDFCGOLD", "HDFCLIFE", "HDFCSILVER", "HEROMOTOCO", "HINDALCO",
    "HINDPETRO", "ICICIBANK", "ICICIGI", "ICICIPRULI", "IDFCFIRSTB", "IEX",
    "IGL", "INDHOTEL", "INDIANB", "INDIGO", "INDUSINDBK", "INDUSTOWER", "INFY",
    "IOC", "IPCALAB", "IRCTC", "IREDA", "IRFC", "ITC", "JINDALSTEL", "JIOFIN",
    "JKCEMENT", "JSWENERGY", "JSWSTEEL", "JUBLFOOD", "KOTAKBANK", "KPITTECH",
    "LALPATHLAB", "LAURUSLABS", "LICHSGFIN", "LICI", "LINDEINDIA", "LODHA",
    "LT", "LTIM", "LTTS", "LUPIN", "M&M", "M&MFIN", "MARICO", "MARUTI",
    "MAXHEALTH", "MAZDOCK", "MCX", "MFSL", "MOTHERSON", "MPHASIS", "MRF",
    "MSUMI", "MUTHOOTFIN", "NATIONALUM", "NAUKRI", "NAVINFLUOR", "NELCO",
    "NESTLEIND", "NHPC", "NIFTY", "NMDC", "NTPC", "OBEROIRLTY", "OIL", "ONGC",
    "PAGEIND", "PATANJALI", "PAYTM", "PERSISTENT", "PETRONET", "PFC", "PGHH",
    "PIDILITIND", "PIIND", "PNB", "PNBHOUSING", "POLICYBZR", "POLYCAB",
    "POONAWALLA", "POWERGRID", "POWERINDIA", "PRESTIGE", "RAILTEL", "RAMCOCEM",
    "RECLTD", "RELIANCE", "ROUTE", "RVNL", "SAIL", "SBICARD", "SBILIFE", "SBIN",
    "SHREECEM", "SHRIRAMFIN", "SIEMENS", "SONACOMS", "SRF", "SUNPHARMA",
    "SUNTV", "SYNGENE", "TANLA", "TATACHEM", "TATACOMM", "TATACONSUM",
    "TATAELXSI", "TATAPOWER", "TATASTEEL", "TATATECH", "TCS", "TECHM",
    "TEJASNET", "TIINDIA", "TITAN", "TMPV", "TORNTPHARM", "TORNTPOWER",
    "TRENT", "TVSMOTOR", "UBL", "ULTRACEMCO", "UNITDSPR", "VBL", "VEDL",
    "VOLTAS", "HINDCOPPER", "NDIA",
]
us100_raw = [
    "PLTR", "ARM", "INTC", "AMD", "MU", "QCOM", "LRCX", "MCHP", "AVGO", "AMAT",
    "GFS", "TXN", "IDXX", "DDOG", "ZS", "TRI", "CSCO", "ADI", "PANW", "ORCL",
    "AXON", "CRWD", "ASML", "SLV", "CHTR", "TTD", "SHOP", "NAS100", "APP",
    "BIIB", "FUTU", "PCAR", "NVDA", "FTNT", "MSFT", "FAST", "VRTX", "US30",
    "WDAY", "CDNS", "SPX", "ORLY", "ON", "CSX", "TSLA", "AAPL", "SBUX", "GLD",
    "ADBE", "PDD", "LIN", "BKR", "GOOGL", "HON", "PYPL", "INTU", "ADSK",
    "CMCSA", "DASH", "ROST", "GILD", "KHC", "CTAS", "AEP", "EA", "DXCM",
    "XEL", "GEHC", "BKNG", "MDLZ", "EXC", "WBD", "MNST", "LULU", "TMUS",
    "PEP", "ADP", "NFLX", "ABNB", "COST", "CTSH", "MELI", "TTWO", "META",
    "CSGP", "CEG", "AMZN", "ISRG", "CCEP", "FANG",
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
COMMODITIES = [
    ("GC=F", "GOLD"),
    ("SI=F", "SILVER"),
    ("KC=F", "COFFEE"),
    ("CL=F", "CRUDE"),
    ("NG=F", "GAS"),
    ("^VIX", "VIX"),
]
FOREX_PAIRS = [
    ("EURUSD=X", "EUR/USD"),
    ("GBPUSD=X", "GBP/USD"),
    ("USDJPY=X", "USD/JPY"),
    ("AUDUSD=X", "AUD/USD"),
    ("USDCAD=X", "USD/CAD"),
]
WATCHLIST_CATEGORIES = {
    "Commodities": COMMODITIES,
    "Forex": FOREX_PAIRS,
    "Nifty200": list(zip(nifty200_yf, nifty200_raw)),
    "US100": list(zip(us100_yf, us100_raw + ["IXIC"])),
}
DISPLAY_TO_SYMBOL = {}
for _cat_symbols in WATCHLIST_CATEGORIES.values():
  for _sym, _disp in _cat_symbols:
    DISPLAY_TO_SYMBOL[_disp] = _sym
VIEWS = ["📊 Charts", "🔎 Scanner"]
TIMEFRAME_PERIODS = {
    "15m": "10d",
    "30m": "20d",
    "60m": "60d",
    "4h": "180d",
    "1d": "1y",
    "1wk": "5y",
}

# =====================================================================
# CHARTING & PLOTTING
# =====================================================================
def add_buy_sell_markers(
    fig,
    x_vals,
    signal_series,
    low_series,
    high_series,
    row,
    col,
    buy_offset=0.995,
    sell_offset=1.005,
    absolute_offset=None,
):
  signal_arr = np.asarray(signal_series)
  x_arr = np.asarray(x_vals)
  low_arr = np.asarray(low_series, dtype=float)
  high_arr = np.asarray(high_series, dtype=float)
  if absolute_offset is not None:
    buy_y_arr = low_arr - absolute_offset
    sell_y_arr = high_arr + absolute_offset
  else:
    buy_y_arr = low_arr * buy_offset
    sell_y_arr = high_arr * sell_offset
  for i in range(len(signal_arr)):
    sig = signal_arr[i]
    if sig == "BUY":
      fig.add_annotation(
          x=x_arr[i],
          y=buy_y_arr[i],
          text="<b>BUY</b>",
          showarrow=False,
          font=dict(color="#0B0E11", size=9),
          bgcolor=COLOR_GREEN,
          bordercolor=COLOR_GREEN,
          borderwidth=1,
          borderpad=2,
          opacity=0.95,
          yanchor="top",
          row=row,
          col=col,
      )
    elif sig == "SELL":
      fig.add_annotation(
          x=x_arr[i],
          y=sell_y_arr[i],
          text="<b>SELL</b>",
          showarrow=False,
          font=dict(color="#FFFFFF", size=9),
          bgcolor=COLOR_RED,
          bordercolor=COLOR_RED,
          borderwidth=1,
          borderpad=2,
          opacity=0.95,
          yanchor="bottom",
          row=row,
          col=col,
      )

def create_chart_figure(
    renko_df, ha_df, brick_size, display, ema_fast, ema_slow, ema_mid=None
):
  x_renko = list(range(len(renko_df)))
  x_ha = x_renko
  n_ticks = min(10, len(renko_df))
  if n_ticks > 0 and "Date" in renko_df.columns:
    tick_indices = np.linspace(0, len(renko_df) - 1, n_ticks, dtype=int)
    tick_vals = [x_renko[i] for i in tick_indices]
    tick_texts = []
    for i in tick_indices:
      dt = renko_df["Date"].iloc[i]
      if hasattr(dt, "strftime"):
        tick_texts.append(dt.strftime("%d-%m %H:%M" if (dt.hour != 0 or dt.minute != 0) else "%d-%m"))
      else:
        tick_texts.append(str(dt))
  else:
    tick_vals, tick_texts = [], []

  fig = make_subplots(
      rows=4,
      cols=1,
      shared_xaxes=True,
      row_heights=[0.28, 0.28, 0.22, 0.22],
      vertical_spacing=0.03,
      subplot_titles=(
          f"{display} — Heikin Ashi",
          f"{display} — ATR Renko",
          "TradingView MACD (Crossover Signals)",
          "RSI (Buy/Sell Signals with Levels 30 & 70)",
      ),
  )
  
  # Subplot 1: Heikin Ashi
  fig.add_trace(
      go.Candlestick(
          x=x_ha, open=ha_df["Open"], high=ha_df["High"], low=ha_df["Low"], close=ha_df["Close"],
          increasing_line_color=COLOR_BULL, decreasing_line_color=COLOR_BEAR,
          increasing_fillcolor=COLOR_BULL, decreasing_fillcolor=COLOR_BEAR, showlegend=False,
      ), row=1, col=1,
  )
  fig.add_trace(go.Scatter(x=x_ha, y=ha_df["EMA_FAST"], line=dict(color=COLOR_MA_FAST, width=1.5), showlegend=False), row=1, col=1)
  fig.add_trace(go.Scatter(x=x_ha, y=ha_df["EMA_SLOW"], line=dict(color=COLOR_MA_SLOW, width=1.5), showlegend=False), row=1, col=1)
  if ema_mid is not None and "EMA_MID" in ha_df.columns:
    fig.add_trace(go.Scatter(x=x_ha, y=ha_df["EMA_MID"], line=dict(color="#FFFFFF", width=1.3), showlegend=False), row=1, col=1)
  add_buy_sell_markers(fig, x_ha, ha_df["Signal"], ha_df["Low"], ha_df["High"], row=1, col=1)

  # Subplot 2: ATR Renko
  fig.add_trace(
      go.Candlestick(
          x=x_renko, open=renko_df["Open"], high=renko_df["High"], low=renko_df["Low"], close=renko_df["Close"],
          increasing_line_color=COLOR_BULL, decreasing_line_color=COLOR_BEAR,
          increasing_fillcolor=COLOR_BULL, decreasing_fillcolor=COLOR_BEAR, showlegend=False,
      ), row=2, col=1,
  )
  fig.add_trace(go.Scatter(x=x_renko, y=renko_df["EMA_FAST"], line=dict(color=COLOR_MA_FAST, width=1.5), showlegend=False), row=2, col=1)
  fig.add_trace(go.Scatter(x=x_renko, y=renko_df["EMA_SLOW"], line=dict(color=COLOR_MA_SLOW, width=1.5), showlegend=False), row=2, col=1)
  if ema_mid is not None and "EMA_MID" in renko_df.columns:
    fig.add_trace(go.Scatter(x=x_renko, y=renko_df["EMA_MID"], line=dict(color="#FFFFFF", width=1.3), showlegend=False), row=2, col=1)
  add_buy_sell_markers(fig, x_renko, renko_df["Confirmed_Signal"], renko_df["Low"], renko_df["High"], row=2, col=1)

  # Structure lines
  last_struct_event = latest_structure_event(renko_df, lookback=len(renko_df))
  struct_style = {
      "BOS_DEMAND": (COLOR_BOS_DEMAND, "B-S"),
      "BOS_SUPPLY": (COLOR_BOS_SUPPLY, "B-D"),
      "CHOCH_DEMAND": (COLOR_CHOCH_DEMAND, "CH-S"),
      "CHOCH_SUPPLY": (COLOR_CHOCH_SUPPLY, "CH-D"),
  }
  if last_struct_event is not None:
    s_type = last_struct_event["type"]
    if s_type in struct_style:
      color, label = struct_style[s_type]
      s_level = last_struct_event["level"]
      i = len(renko_df) - 1 - last_struct_event["bars_ago"]
      origin_idx = renko_df["StructureOriginIdx"].iloc[i]
      span_start = int(origin_idx) if pd.notna(origin_idx) else max(i - 6, 0)
      fig.add_shape(
          type="line", x0=span_start, x1=len(renko_df) - 1, y0=s_level, y1=s_level,
          line=dict(color=color, width=1.5, dash="dash"), opacity=0.6, row=2, col=1,
      )
      fig.add_annotation(
          x=i, y=s_level, text=label, showarrow=False, font=dict(color="#FFFFFF", size=10),
          bgcolor="#1E222D", bordercolor=color, borderwidth=1, row=2, col=1,
          yshift=14 if s_type in ("BOS_DEMAND", "CHOCH_DEMAND") else -14,
      )

  # Subplot 3: MACD with Crossover Buy/Sell Signals
  hist_vals = renko_df["MACD_Hist"].values
  hist_colors = [COLOR_GREEN if v >= 0 else COLOR_RED for v in hist_vals]
  fig.add_trace(go.Bar(x=x_renko, y=hist_vals, marker_color=hist_colors, opacity=0.85, showlegend=False), row=3, col=1)
  fig.add_trace(go.Scatter(x=x_renko, y=renko_df["MACD"], line=dict(color=COLOR_MACD_LINE, width=1.8), showlegend=False), row=3, col=1)
  fig.add_trace(go.Scatter(x=x_renko, y=renko_df["MACD_Signal"], line=dict(color=COLOR_SIGNAL_LINE, width=1.8), showlegend=False), row=3, col=1)
  fig.add_hline(y=0, line=dict(color=COLOR_ZERO_LINE, width=1), row=3, col=1)
  
  macd_vals = renko_df["MACD"].values
  macd_finite = macd_vals[np.isfinite(macd_vals)]
  macd_pad = ((macd_finite.max() - macd_finite.min()) * 0.12 or 0.001) if macd_finite.size else 0.001
  add_buy_sell_markers(fig, x_renko, renko_df["Div_Signal"], renko_df["MACD"], renko_df["MACD"], row=3, col=1, absolute_offset=macd_pad)

  # Subplot 4: RSI
  rsi_vals = renko_df["RSI"].values
  fig.add_trace(go.Scatter(x=x_renko, y=rsi_vals, line=dict(color="#00D4FF", width=1.8), showlegend=False), row=4, col=1)
  fig.add_hline(y=70, line=dict(color=COLOR_RED, width=1, dash="dash"), row=4, col=1)
  fig.add_hline(y=30, line=dict(color=COLOR_GREEN, width=1, dash="dash"), row=4, col=1)
  fig.update_yaxes(range=[0, 100], row=4, col=1)
  add_buy_sell_markers(fig, x_renko, renko_df["RSI_Signal"], renko_df["RSI"], renko_df["RSI"], row=4, col=1, absolute_offset=5.0)

  fig.update_layout(
      height=850,
      paper_bgcolor=COLOR_BG_DARK,
      plot_bgcolor=COLOR_BG_DARK,
      font=dict(color=COLOR_TEXT_MUTED, size=10),
      showlegend=False,
      margin=dict(l=10, r=70, t=40, b=10),
      xaxis_rangeslider_visible=False,
      xaxis2_rangeslider_visible=False,
  )
  for r in range(1, 5):
    kwargs = {"showgrid": False, "row": r, "col": 1, "matches": "x", "tickfont": dict(size=10)}
    if r == 4 and tick_vals:
      kwargs["tickvals"] = tick_vals
      kwargs["ticktext"] = tick_texts
      kwargs["showticklabels"] = True
    fig.update_xaxes(**kwargs)
    fig.update_yaxes(
        gridcolor="#2A2F3A", side="right", row=r, col=1,
        tickformat="f", hoverformat="f", tickfont=dict(size=10),
        automargin=True, ticklabelposition="outside right",
    )
  return fig

def go_to_chart(symbol, display):
  st.session_state.chart_symbol = symbol
  st.session_state.chart_display = display
  st.session_state.active_view = VIEWS[0]

def render_zoomable_chart(fig, key, height=850):
  fig_json = fig.to_json()
  div_id = f"qfx_chart_{key}"
  html = f"""
    <div id="{div_id}_wrapper" style="
        resize: both; overflow: auto; width: 100%; height: {height}px;
        min-width: 320px; min-height: 400px; max-width: 100%;
        border: 1px solid {COLOR_BORDER}; border-radius: 6px;
        background-color: {COLOR_BG_DARK}; padding: 4px; box-sizing: border-box;">
      <div id="{div_id}" style="width: 100%; height: 100%;"></div>
    </div>
    <div style="font-size:10px;color:{COLOR_TEXT_MUTED};margin-top:4px;">
      🖱️ Scroll to zoom • Drag to box-zoom • Drag corner to resize
    </div>
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <script>
      (function() {{
        var figSpec = {fig_json};
        var config = {{scrollZoom: true, displaylogo: false, responsive: false}};
        var el = document.getElementById("{div_id}");
        Plotly.newPlot(el, figSpec.data, figSpec.layout, config).then(function() {{
          var annotations = el.querySelectorAll('.annotation');
          annotations.forEach(function(ann) {{
            var textEl = ann.querySelector('text');
            if (textEl && (textEl.textContent.includes('BUY') || textEl.textContent.includes('SELL'))) {{
              ann.classList.add('qfx-blinking-signal');
            }}
          }});
        }});
        var wrapper = document.getElementById("{div_id}_wrapper");
        if (window.ResizeObserver) {{
          var ro = new ResizeObserver(function() {{
            Plotly.Plots.resize(el);
          }});
          ro.observe(wrapper);
        }}
      }})();
    </script>
    """
  components.html(html, height=height + 60, scrolling=True)

def _render_clickable_html(marker, inner_html, extra_style="", key_prefix=None, on_click=None, args=None):
  with st.container():
    st.markdown(f"<div class='{marker}' style='cursor:pointer;{extra_style}'>{inner_html}</div>", unsafe_allow_html=True)
    st.markdown(
        f"""<style>
            div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .{marker}),
            div[data-testid="stVerticalBlock"]:has(.{marker}):has(button) {{
                position: relative;
            }}
            div[data-testid="stVerticalBlock"]:has(.{marker}) div[data-testid="stButton"] {{
                position: absolute;
                inset: 0;
                margin: 0;
                z-index: 5;
            }}
            div[data-testid="stVerticalBlock"]:has(.{marker}) div[data-testid="stButton"] button {{
                width: 100%;
                height: 100%;
                min-height: 100%;
                opacity: 0;
                cursor: pointer;
                padding: 0;
                border: none;
                background: transparent;
            }}
            .{marker}:hover {{ border-color: {COLOR_TEXT_MUTED} !important; }}
            </style>""",
        unsafe_allow_html=True,
    )
    st.button(" ", key=f"{key_prefix}_btn", on_click=on_click, args=args)

def render_clickable_single_box(title, movers, key_prefix, on_click, compact=False):
  pad = "3px 8px" if compact else "8px 12px"
  font_sz = "10px" if compact else "11px"
  margin_b = "0px" if compact else "8px"
  if not movers:
    st.markdown(
        f"<div style='background-color:{COLOR_PANEL_BG};border:1px solid {COLOR_BORDER};"
        f"border-radius:6px;padding:{pad};margin-bottom:{margin_b};'>"
        f"<div style='font-size:{font_sz};color:{COLOR_TEXT_MUTED};font-weight:600;'>{title}:"
        f" <span style='color:{COLOR_TEXT_MUTED};font-weight:400;'>No data</span></div></div>",
        unsafe_allow_html=True,
    )
    return
  best = movers[0]
  color = COLOR_GREEN if best["chg"] >= 0 else COLOR_RED
  arrow = "▲" if best["chg"] >= 0 else "▼"
  price_str = f"${format_price(best['price'])}"
  if compact:
    inner = (
        f"<div style='font-size:{font_sz};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>"
        f"<span style='color:{COLOR_TEXT_MUTED};font-weight:600;'>{title}:</span>"
        f" <span style='font-weight:700;color:{COLOR_TEXT_MAIN};'>{best['display']}</span>"
        f" <span style='color:{COLOR_TEXT_MUTED};'>{price_str}</span>"
        f" <span style='color:{color};'>{arrow} {best['chg']:+.2f}%</span>"
        f"</div>"
    )
  else:
    inner = (
        f"<div style='font-size:11px;color:{COLOR_TEXT_MUTED};margin-bottom:4px;font-weight:600;'>{title}</div>"
        f"<div style='font-size:11px;font-weight:700;color:{COLOR_TEXT_MAIN};'>{best['display']}</div>"
        f"<div style='font-size:11px;color:{COLOR_TEXT_MUTED};'>{price_str}</div>"
        f"<div style='font-size:11px;color:{color};'>{arrow} {best['chg']:+.2f}%</div>"
    )
  marker = f"qfx-hit-{key_prefix}"
  _render_clickable_html(
      marker, inner, extra_style=f"background-color:{COLOR_PANEL_BG};border:1px solid {COLOR_BORDER};border-radius:6px;padding:{pad};margin-bottom:{margin_b};",
      key_prefix=key_prefix, on_click=on_click, args=(best["symbol"], best["display"]),
  )

def render_clickable_list_box(title, movers, key_prefix, on_click, value_fmt=None):
  st.markdown(
      f"<div style='background-color:{COLOR_PANEL_BG};border:1px solid {COLOR_BORDER};"
      f"border-radius:6px 6px 0 0;padding:8px 12px 6px 12px;margin-bottom:0px;'>"
      f"<div style='font-size:12px;color:{COLOR_TEXT_MUTED};font-weight:600;'>{title}</div></div>",
      unsafe_allow_html=True,
  )
  if not movers:
    st.markdown(
        f"<div style='background-color:{COLOR_PANEL_BG};border:1px solid {COLOR_BORDER};"
        f"border-top:none;border-radius:0 0 6px 6px;padding:8px 12px;margin-bottom:14px;"
        f"font-size:12px;color:{COLOR_TEXT_MUTED};'>No data</div>",
        unsafe_allow_html=True,
    )
    return
  n = len(movers)
  for idx, m in enumerate(movers, start=1):
    is_last = idx == n
    color = COLOR_GREEN if m["chg"] >= 0 else COLOR_RED
    arrow = "▲" if m["chg"] >= 0 else "▼"
    value_html = value_fmt(m) if value_fmt else f"<span style='color:{color};white-space:nowrap;'>{arrow} {m['chg']:+.2f}%</span>"
    inner = (
        f"<div style='font-size:12px;display:flex;justify-content:space-between;gap:8px;color:{COLOR_TEXT_MAIN};line-height:1.6;'>"
        f"<span>{idx}. {m['display']}</span>{value_html}</div>"
    )
    radius = "0 0 6px 6px" if is_last else "0"
    margin = "14px" if is_last else "0px"
    marker = f"qfx-hit-{key_prefix}-{idx}"
    _render_clickable_html(
        marker, inner, extra_style=f"background-color:{COLOR_PANEL_BG};border:1px solid {COLOR_BORDER};border-top:none;border-radius:{radius};padding:7px 12px;margin-bottom:{margin};",
        key_prefix=f"{key_prefix}_{idx}", on_click=on_click, args=(m["symbol"], m["display"]),
    )

# =====================================================================
# SIDEBAR CONTROLS
# =====================================================================
st.sidebar.markdown("## 📈 QuantFX Terminal")
st.sidebar.caption("ATR Renko • Heikin Ashi • MACD Crossovers")
symbol_mode = st.sidebar.radio("Symbol source", ["Presets", "Custom"], horizontal=True)
if symbol_mode == "Presets":
  preset_cat = st.sidebar.selectbox("Category", list(WATCHLIST_CATEGORIES.keys()))
  options = WATCHLIST_CATEGORIES[preset_cat]
  choice = st.sidebar.selectbox("Symbol", options, format_func=lambda t: t[1])
  current_symbol, current_display = choice
else:
  current_symbol = st.sidebar.text_input("Yahoo Finance symbol", value="GC=F")
  current_display = st.sidebar.text_input("Display name", value=current_symbol)
interval = st.sidebar.select_slider("Timeframe", options=list(TIMEFRAME_PERIODS.keys()), value="1d")
period = TIMEFRAME_PERIODS[interval]

st.sidebar.markdown("---")
c1, c2, c2b = st.sidebar.columns(3)
ema_fast = c1.number_input("EMA Fast", min_value=1, max_value=200, value=21)
ema_mid = c2.number_input("EMA Mid", min_value=1, max_value=200, value=34)
ema_slow = c2b.number_input("EMA Slow", min_value=1, max_value=200, value=50)
c3, c4 = st.sidebar.columns(2)
atr_period = c3.number_input("ATR Period", min_value=2, max_value=100, value=21)
atr_multiplier = c4.number_input("ATR Mult.", min_value=0.1, max_value=10.0, value=3.0, step=0.1)

st.sidebar.markdown("---")
st.sidebar.markdown("**MACD Settings**")
mc1, mc2, mc3 = st.sidebar.columns(3)
macd_fast = mc1.number_input("Fast", min_value=1, max_value=100, value=12)
macd_slow = mc2.number_input("Slow", min_value=1, max_value=200, value=26)
macd_signal = mc3.number_input("Signal", min_value=1, max_value=100, value=9)

if st.sidebar.button("🔄 Refresh data", use_container_width=True):
  st.cache_data.clear()
  st.rerun()

if "chart_symbol" not in st.session_state:
  st.session_state.chart_symbol = current_symbol
  st.session_state.chart_display = current_display
  st.session_state._prev_sidebar_symbol = current_symbol
elif current_symbol != st.session_state._prev_sidebar_symbol:
  st.session_state.chart_symbol = current_symbol
  st.session_state.chart_display = current_display
  st.session_state._prev_sidebar_symbol = current_symbol

chart_symbol = st.session_state.chart_symbol
chart_display = st.session_state.chart_display

# Fetch initial raw data for live price display
raw_df_preview = fetch_live_ohlc(chart_symbol, period=period, interval=interval)
last_price_val = float(raw_df_preview['Close'].iloc[-1]) if not raw_df_preview.empty else 0.0
prev_price_val = float(raw_df_preview['Close'].iloc[-2]) if not raw_df_preview.empty and len(raw_df_preview) > 1 else last_price_val
price_chg_pct = ((last_price_val - prev_price_val) / prev_price_val * 100) if prev_price_val else 0.0
price_color = COLOR_GREEN if price_chg_pct >= 0 else COLOR_RED
price_arrow = "▲" if price_chg_pct >= 0 else "▼"

# =====================================================================
# MAIN LAYOUT: TOP BAR WITH STOCK NAME, LIVE PRICE & VIEWS
# =====================================================================
top_bar_cols = st.columns([0.45, 0.35, 0.2])
with top_bar_cols[0]:
  st.markdown(
      f"<div style='display:flex; align-items:center; gap:10px; flex-wrap:wrap;'>"
      f"<h2>{chart_display}</h2>"
      f"<span style='background-color:{COLOR_PANEL_BG}; border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 10px; font-size:12px; font-weight:700; color:{COLOR_TEXT_MAIN};'>"
      f"${format_price(last_price_val)} <span style='color:{price_color};'>{price_arrow} {price_chg_pct:+.2f}%</span>"
      f"</span>"
      f"</div>",
      unsafe_allow_html=True,
  )
with top_bar_cols[1]:
  if "active_view" not in st.session_state:
    st.session_state.active_view = VIEWS[0]
  active_view = st.radio("View", VIEWS, horizontal=True, label_visibility="collapsed", key="active_view")
with top_bar_cols[2]:
  _header_top_commodity = fetch_top_n_movers(tuple(COMMODITIES), n=1)
  render_clickable_single_box("Top Commodity", _header_top_commodity, key_prefix="header_top_commodity", on_click=go_to_chart, compact=True)

# ---- Charts View --------------------------------------------------------
if active_view == "📊 Charts":
  with st.spinner(f"Fetching {chart_display}..."):
    raw_df = fetch_live_ohlc(chart_symbol, period=period, interval=interval)
  if raw_df.empty:
    st.error(f"No data returned for {chart_display} ({chart_symbol}).")
  else:
    renko_df, brick_size = build_atr_renko_df(
        raw_df,
        atr_period=atr_period,
        atr_multiplier=atr_multiplier,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        ema_mid=ema_mid,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal=macd_signal,
    )
    if renko_df.empty:
      st.warning("Not enough data to build ATR Renko bricks for this timeframe.")
    else:
      ha_df = compute_heikin_ashi(renko_df, ema_fast=ema_fast, ema_slow=ema_slow, ema_mid=ema_mid)
      struct_event = latest_structure_event(renko_df, lookback=15)
      
      fig = create_chart_figure(renko_df, ha_df, brick_size, chart_display, ema_fast, ema_slow, ema_mid)
      
      chart_col, right_panel_col = st.columns([0.74, 0.26])
      with chart_col:
        search_col, search_btn_col = st.columns([0.85, 0.15])
        search_col.text_input(
            "Quick search",
            key="chart_search_box",
            label_visibility="collapsed",
            placeholder="🔍 Search a symbol to open its chart — e.g. GOLD, MU, EUR/USD...",
            on_change=lambda: go_to_chart(st.session_state.get("chart_search_box", "").strip().upper(), st.session_state.get("chart_search_box", "").strip().upper()),
        )
        search_btn_col.button(
            "🔍 Open chart",
            key="chart_search_btn",
            use_container_width=True,
            on_click=lambda: go_to_chart(st.session_state.get("chart_search_box", "").strip().upper(), st.session_state.get("chart_search_box", "").strip().upper()),
        )
        render_zoomable_chart(
            fig,
            key=chart_symbol.replace("=", "_").replace("^", "idx"),
            height=850,
        )
        last_signal = renko_df["Signal"].iloc[-1]
        last_confirmed = renko_df["Confirmed_Signal"].iloc[-1]
        badge_color = (
            COLOR_GREEN
            if last_confirmed == "BUY"
            else (COLOR_RED if last_confirmed == "SELL" else COLOR_TEXT_MUTED)
        )
        st.markdown(
            "Confirmed signal: <span class='qfx-badge qfx-blinking-signal'"
            f" style='background:{badge_color}22;color:{badge_color};'>{last_confirmed}</span>"
            f"&nbsp;&nbsp;•&nbsp;&nbsp;EMA trend: <b>{last_signal}</b>",
            unsafe_allow_html=True,
        )
      with right_panel_col:
        CHARTINK_EMA_SCREENER_URL = "https://chartink.com/screener/ema9-20-cross-5"
        st.markdown(f"<div style='font-size:11px;color:{COLOR_TEXT_MUTED};font-weight:600;margin-bottom:6px;'>📊 Chartink Screener</div>", unsafe_allow_html=True)
        _sidebar_chartink_hits = fetch_chartink_screener(CHARTINK_EMA_SCREENER_URL)
        render_clickable_list_box(
            "Chartink — EMA 9/20 Cross",
            _sidebar_chartink_hits,
            key_prefix="chartink_ema920_sidebar",
            on_click=go_to_chart,
        )

# ---- Scanner View ---------------------------------------------------------
elif active_view == "🔎 Scanner":
  st.caption("Scan watchlists for market indicators. Click any result to load it in the chart view.")
  cats = st.multiselect("Watchlists to scan", list(WATCHLIST_CATEGORIES.keys()), default=["Commodities", "Forex"])
  if st.button("▶️ Run scanner", type="primary"):
    if not cats:
      st.warning("Pick at least one watchlist.")
    else:
      results = []
      for cat in cats:
        for sym, disp in WATCHLIST_CATEGORIES[cat]:
          df_scan = fetch_live_ohlc(sym, period="3mo", interval="1d")
          if not df_scan.empty:
            last_p = float(df_scan["Close"].iloc[-1])
            prev_p = float(df_scan["Close"].iloc[-2]) if len(df_scan) > 1 else last_p
            chg = ((last_p - prev_p) / prev_p) * 100
            results.append({
                "Ticker": disp,
                "RawSymbol": sym,
                "Price": f"${format_price(last_p)}",
                "ChangePct": f"{chg:+.2f}%",
                "Signal": "BUY" if chg >= 0 else "SELL",
            })
      st.session_state["scanner_results"] = pd.DataFrame(results)
      
  df_res = st.session_state.get("scanner_results")
  if df_res is not None and not df_res.empty:
    st.dataframe(df_res, use_container_width=True, hide_index=True)
    sel_ticker = st.selectbox("Open a result in the chart", df_res["Ticker"].tolist(), key="scanner_open_select")
    sel_row = df_res[df_res["Ticker"] == sel_ticker].iloc[0]
    st.button(
        "📈 Open chart",
        key="scanner_open_btn",
        on_click=go_to_chart,
        args=(sel_row["RawSymbol"], sel_row["Ticker"]),
    )
  elif df_res is not None:
    st.info("No results found.")
