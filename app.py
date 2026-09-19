"""
QuantFX Terminal — ATR Renko & Macro Smart Money Structure
Streamlit rewrite with custom candle coloring, right-side axes,
Heikin Ashi EMAs, single-fire pullback signals with blinking animation,
blinking/ticking buy/sell markers on Heikin Ashi, Renko, MACD, and RSI,
expanded box heights, targeted multi-market Telegram alerts,
full share price display, and right-side top mover cards.
v2 additions:
- Smoothed MACD line/signal/histogram (adjustable "MACD Smoothing" slider).
- Larger button-style BUY/SELL badges on the MACD panel.
- RSI buy/sell markers now reuse the exact same combined signal as the
  MACD panel, so the two rows always fire on the same bricks.
- Vertical stock name + live price watermark running up the left edge
  of the chart.
v3 additions:
- Unified Master_Signal: EMA9/21/50 alignment + MACD agreement + RSI
  exhaustion filter + cooldown, shared by every chart panel.
- Dedicated MACD-line-crosses-signal-line scanners: 2H for US100/Nifty500,
  30M for Commodities/Forex, shown as scanner boxes and wired into the
  Telegram auto-scan button (BUY-only for US100/Nifty500, BUY+SELL for
  Commodities/Forex).
v4 additions:
- Nifty200 watchlist retired; all India-side scanning, charting, and
  alerts now run across the full Nifty500 list (sourced from
  ind_nifty500list.csv).
v5 additions:
- Telegram auto-scan trimmed to exactly two alert types: High-Conviction
  BUY (US100/Nifty500) and 30m 3-EMA cross, either side (Commodities/Forex).
- Long Telegram messages are now split into multiple sends to avoid the
  "message is too long" Bad Request error.
- Scheduled auto-scan: pick 1h/2h/4h and the app will re-scan and push
  Telegram alerts automatically on that cadence (needs the
  `streamlit-autorefresh` package — pip install streamlit-autorefresh).
v6 additions:
- "High-Conviction Shares" box now runs the daily EMA-9 pullback clause
  (close > EMA200, EMA9 > EMA200, EMA9 > EMA20, RSI14 > 50, close above the
  5- and 10-day-ago highs, low <= EMA9 < close, volume > 20d avg volume) and
  is split into Nifty 500 / US 100 / Commodities / Forex.
- Telegram: first scan sends the full list; every later scan sends only the
  stocks that were NOT in the previous scan's list (state is kept in
  .qfx_conviction_state.json next to this file).
- All MACD scanner boxes removed from the right-hand panel.
v7 additions:
- Right-side stock rows are real buttons: click any stock / commodity / forex
  row and its chart opens immediately.
- MACD settings live in a collapsed left-sidebar expander and can be saved
  (.qfx_settings.json).
v8 additions:
- Heikin Ashi panel is now built from the real candles (EMA ribbon, dashed bands,
  Buy/Sell pills, BOS/CHoCH label) and the MACD panel is a TradingView-style
  4-colour histogram computed independently from the real candles, with its own
  Buy/Sell (MACD x Signal). Renko + RSI keep their brick-based signals.
v9 additions:
- EMA 9 x 27 cross screener boxes (2H) for Nifty 500 and US 100 (EMA Mid default is now 27).
- Renko (and RSI) Buy/Sell now fire on the EMA 9 x 27 cross; MACD histogram drawn as tiny separated bricks.

v10 additions:
- Panel order is now Heikin Ashi -> ATR Renko -> MACD -> RSI.
- Heikin Ashi: EMA colour fill removed; candles use the same colours as the Renko bricks.
- All four panels zoom / pan / reset together (Renko bricks are mapped onto the real-candle timeline).
v11 additions:
- Drag = pan (left / right / up / down) and every panel moves with it; zoom in / out (wheel, box, axis drag,
  modebar) and Reset also act on all four panels together. Vertical moves / zooms are copied as the same
  fraction of each panel's own range (price, MACD and RSI have different scales).
- Mobile: 1 finger pans, 2 fingers pinch-zoom, all panels follow; "Touch: pan chart / scroll page" button
  lets you scroll the page when the chart fills the screen; "Reset view" button under the chart.
- Right-side stock rows are forced to start at the left edge of each box.
"""
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
try:
  from streamlit_autorefresh import st_autorefresh
  AUTOREFRESH_AVAILABLE = True
except ImportError:
  AUTOREFRESH_AVAILABLE = False
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
    /* Clickable stock rows (real Streamlit buttons -> reliable click-to-chart) */
    div[class*="st-key-qfxrow_"] {{ margin-top: -0.35rem !important; }}
    div[class*="st-key-qfxrow_"] button {{
        width: 100%; min-height: 0; padding: 6px 12px;
        background-color: {COLOR_PANEL_BG}; color: {COLOR_TEXT_MAIN};
        border: 1px solid {COLOR_BORDER}; border-top: none; border-radius: 0;
        justify-content: flex-start;
    }}
    div[class*="st-key-qfxrow_"] button:hover {{
        background-color: #171C27; border-color: {COLOR_TEXT_MUTED};
    }}
    div[class*="st-key-qfxrow_"] button p,
    div[class*="st-key-qfxtop_"] button p {{
        font-size: 12px; text-align: left; margin: 0;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }}
    /* Right-side stock rows: label always starts at the LEFT edge (never centred) */
    div[class*="st-key-qfxrow_"] div[data-testid="stButton"],
    div[class*="st-key-qfxrow_"] div[data-testid="stElementContainer"] {{
        width: 100% !important;
    }}
    div[class*="st-key-qfxrow_"] button {{
        display: flex !important;
        justify-content: flex-start !important;
        align-items: center !important;
        text-align: left !important;
        width: 100% !important;
    }}
    div[class*="st-key-qfxrow_"] button > div,
    div[class*="st-key-qfxrow_"] button [data-testid="stMarkdownContainer"],
    div[class*="st-key-qfxrow_"] button p {{
        display: block !important;
        width: 100% !important;
        margin: 0 !important;
        text-align: left !important;
        justify-content: flex-start !important;
    }}
    div[class*="st-key-qfxtop_"] button {{
        width: 100%; min-height: 0; padding: 4px 8px;
        background-color: {COLOR_PANEL_BG}; color: {COLOR_TEXT_MAIN};
        border: 1px solid {COLOR_BORDER}; border-radius: 6px; justify-content: flex-start;
    }}
    div[class*="st-key-qfxtop_"] button:hover {{ border-color: {COLOR_TEXT_MUTED}; }}
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
        margin-bottom: 0.2rem !important;
        padding-bottom: 0 !important;
        padding-top: 4px !important;
        font-size: 1.35rem !important;
        line-height: 1.5 !important;
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
def _split_message_into_chunks(message, max_len=3800):
  """Split a long message into Telegram-safe chunks (<=4096 chars, we use
  a smaller cap for headroom). Splits on line boundaries so a single alert
  line is never cut in half; falls back to a hard split only if one line
  alone exceeds max_len."""
  lines = message.split("\n")
  chunks = []
  current = ""
  for line in lines:
    candidate = f"{current}\n{line}" if current else line
    if len(candidate) <= max_len:
      current = candidate
    else:
      if current:
        chunks.append(current)
      if len(line) <= max_len:
        current = line
      else:
        for i in range(0, len(line), max_len):
          chunks.append(line[i:i + max_len])
        current = ""
  if current:
    chunks.append(current)
  return chunks or [message]
def send_telegram_alert_chunked(message, token, chat_id, max_len=3800):
  """Send a (possibly long) message as multiple Telegram messages so a
  large scan result never triggers Telegram's 'message is too long' error.
  Returns (all_ok, status_text)."""
  chunks = _split_message_into_chunks(message, max_len=max_len)
  total = len(chunks)
  all_ok = True
  last_err = ""
  for i, chunk in enumerate(chunks, start=1):
    part_label = f" (part {i}/{total})" if total > 1 else ""
    ok, msg = send_telegram_alert(chunk + part_label if total > 1 else chunk, token, chat_id)
    if not ok:
      all_ok = False
      last_err = msg
  return all_ok, ("Success" if all_ok else last_err)
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
  ha["Low"] = pd.concat([df["Low"], ha["Open"], ha["Close"]], axis=1).min(axis=1)
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
def detect_macd_crossovers(
    renko_df,
    ema_fast_col="EMA_FAST",
    ema_slow_col="EMA_SLOW",
    min_gap_pct=0.10,
    cooldown=3,
):
  macd = renko_df["MACD"].values
  signal = renko_df["MACD_Signal"].values
  n = len(renko_df)
  macd_signals = ["HOLD"] * n
  macd_types = [None] * n
  if n < 2:
    return macd_signals, macd_types
  finite_macd = macd[np.isfinite(macd)]
  macd_range = (finite_macd.max() - finite_macd.min()) if finite_macd.size else 0.0
  noise_floor = macd_range * min_gap_pct if macd_range else 0.0
  has_trend = ema_fast_col in renko_df.columns and ema_slow_col in renko_df.columns
  ema_fast_arr = renko_df[ema_fast_col].values if has_trend else None
  ema_slow_arr = renko_df[ema_slow_col].values if has_trend else None
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
    if abs(macd[i] - signal[i]) < noise_floor:
      continue
    if i - last_fired < cooldown:
      continue
    if crossed_up:
      if has_trend and ema_fast_arr[i] < ema_slow_arr[i]:
        continue
      macd_signals[i] = "BUY"
      macd_types[i] = "MACD Cross Up"
      last_fired = i
    elif crossed_down:
      if has_trend and ema_fast_arr[i] > ema_slow_arr[i]:
        continue
      macd_signals[i] = "SELL"
      macd_types[i] = "MACD Cross Down"
      last_fired = i
  return macd_signals, macd_types
def detect_rsi_signals(renko_df, min_gap=1.5, cooldown=3):
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
def fetch_2h_ohlc(symbol, period="60d"):
  df = fetch_live_ohlc(symbol, period=period, interval="60m")
  if df.empty:
    return df
  agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
  if "Volume" in df.columns:
    agg["Volume"] = "sum"
  df_2h = df.resample("2h").agg(agg).dropna(subset=["Close"])
  return df_2h
@st.cache_data(ttl=300, show_spinner=False)
def scan_triple_ema_cross_2h(
    symbols_tuple, ema_fast=9, ema_mid=21, ema_slow=50, lookback=1, max_results=6
):
  results = []
  for sym, disp in symbols_tuple:
    try:
      df = fetch_2h_ohlc(sym, period="60d")
      if df.empty or len(df) < ema_slow + 5:
        continue
      close = df["Close"]
      cross = detect_triple_ema_cross_signal(
          close, fast=ema_fast, mid=ema_mid, slow=ema_slow, lookback=lookback
      )
      if not cross:
        continue
      last_price = float(close.iloc[-1])
      prev_price = float(close.iloc[-2]) if len(close) > 1 else last_price
      chg = ((last_price - prev_price) / prev_price) * 100 if prev_price else 0.0
      results.append({
          "symbol": sym,
          "display": disp,
          "price": last_price,
          "chg": chg,
          "direction": cross["direction"],
          "bars_ago": cross["bars_ago"],
      })
    except Exception:
      continue
  results.sort(key=lambda r: r["bars_ago"])
  return results[:max_results]
@st.cache_data(ttl=300, show_spinner=False)
def scan_triple_ema_cross_30m(
    symbols_tuple, ema_fast=9, ema_mid=21, ema_slow=50, lookback=1
):
  results = []
  for sym, disp in symbols_tuple:
    try:
      df = fetch_live_ohlc(sym, period="10d", interval="30m")
      if df.empty or len(df) < ema_slow + 5:
        continue
      cross = detect_triple_ema_cross_signal(
          df["Close"], fast=ema_fast, mid=ema_mid, slow=ema_slow, lookback=lookback
      )
      if cross:
        results.append({"symbol": sym, "display": disp, **cross})
    except Exception:
      continue
  return results
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
def compute_macd_line_cross_signal(renko_df, cooldown=1):
  """
  The literal "blue line crosses orange line" signal: fires BUY the bar the
  MACD line (blue) crosses above the Signal line (orange), and SELL the bar
  it crosses below — no EMA-trend gate, no RSI filter. This is what drives
  the BUY/SELL buttons on every panel (Heikin Ashi, Renko, MACD, RSI) so
  what you see is exactly every real MACD/Signal crossover.
  cooldown=1 means every distinct crossing bar fires; raise it only if you
  want to thin out rapid back-to-back crosses.
  """
  n = len(renko_df)
  out = ["HOLD"] * n
  if n < 2 or "MACD" not in renko_df.columns or "MACD_Signal" not in renko_df.columns:
    return out
  macd = renko_df["MACD"].values
  sig = renko_df["MACD_Signal"].values
  last_fired = -cooldown - 1
  for i in range(1, n):
    if not (np.isfinite(macd[i]) and np.isfinite(sig[i]) and np.isfinite(macd[i - 1]) and np.isfinite(sig[i - 1])):
      continue
    crossed_up = macd[i] > sig[i] and macd[i - 1] <= sig[i - 1]
    crossed_down = macd[i] < sig[i] and macd[i - 1] >= sig[i - 1]
    if crossed_up and (i - last_fired) >= cooldown:
      out[i] = "BUY"
      last_fired = i
    elif crossed_down and (i - last_fired) >= cooldown:
      out[i] = "SELL"
      last_fired = i
  return out
def compute_master_signal(renko_df, cooldown=5, rsi_overbought=70.0, rsi_oversold=30.0):
  """
  Single source of truth for BUY/SELL used across the Heikin Ashi, Renko,
  MACD, and RSI panels alike. A signal only fires when THREE things line
  up on the same bar:
    1) Trend: EMA9/EMA21/EMA50 flip into full bullish (9>21>50) or full
       bearish (9<21<50) alignment (fires once, on the transition bar).
    2) Momentum: MACD line agrees with the direction (above/below signal).
    3) Exhaustion filter: RSI isn't already overbought (for BUY) or
       oversold (for SELL).
  A cooldown between fires stops the flip-flopping you get from any single
  noisy crossover generator.
  """
  n = len(renko_df)
  master = ["HOLD"] * n
  required_cols = ("EMA_FAST", "EMA_MID", "EMA_SLOW", "MACD", "MACD_Signal")
  if n < 2 or any(c not in renko_df.columns for c in required_cols):
    return master
  fast = renko_df["EMA_FAST"].values
  mid = renko_df["EMA_MID"].values
  slow = renko_df["EMA_SLOW"].values
  macd = renko_df["MACD"].values
  macd_sig = renko_df["MACD_Signal"].values
  rsi = renko_df["RSI"].values if "RSI" in renko_df.columns else np.full(n, np.nan)
  last_fired = -cooldown - 1
  for i in range(1, n):
    if not (np.isfinite(fast[i]) and np.isfinite(mid[i]) and np.isfinite(slow[i])
            and np.isfinite(fast[i - 1]) and np.isfinite(mid[i - 1]) and np.isfinite(slow[i - 1])):
      continue
    bullish_now = fast[i] > mid[i] > slow[i]
    bearish_now = fast[i] < mid[i] < slow[i]
    bullish_prev = fast[i - 1] > mid[i - 1] > slow[i - 1]
    bearish_prev = fast[i - 1] < mid[i - 1] < slow[i - 1]
    macd_bull = np.isfinite(macd[i]) and np.isfinite(macd_sig[i]) and macd[i] > macd_sig[i]
    macd_bear = np.isfinite(macd[i]) and np.isfinite(macd_sig[i]) and macd[i] < macd_sig[i]
    rsi_v = rsi[i]
    rsi_ok_buy = np.isnan(rsi_v) or rsi_v < rsi_overbought
    rsi_ok_sell = np.isnan(rsi_v) or rsi_v > rsi_oversold
    if bullish_now and not bullish_prev and macd_bull and rsi_ok_buy and (i - last_fired) >= cooldown:
      master[i] = "BUY"
      last_fired = i
    elif bearish_now and not bearish_prev and macd_bear and rsi_ok_sell and (i - last_fired) >= cooldown:
      master[i] = "SELL"
      last_fired = i
  return master
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
    macd_smooth=3,
    rsi_period=14,
    signal_cooldown=5,
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
  real_macd_raw = real_exp1 - real_exp2
  # Smoothed MACD: run an extra short EMA over the raw MACD line so both the
  # line and the histogram derived from it are less jagged. macd_smooth<=1
  # disables smoothing and falls back to the classic raw MACD line.
  if macd_smooth and macd_smooth > 1:
    real_macd = real_macd_raw.ewm(span=macd_smooth, adjust=False).mean()
  else:
    real_macd = real_macd_raw
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
  
  combined_renko_macd = []
  for i in range(len(renko_df)):
    r_sig = renko_df.loc[i, "Confirmed_Signal"]
    m_sig = macd_sigs[i]
    if r_sig == "BUY" or m_sig == "BUY":
      combined_renko_macd.append("BUY")
    elif r_sig == "SELL" or m_sig == "SELL":
      combined_renko_macd.append("SELL")
    else:
      combined_renko_macd.append("HOLD")
  renko_df["Combined_Renko_MACD_Signal"] = combined_renko_macd
  
  rsi_sigs, rsi_types = detect_rsi_signals(renko_df)
  renko_df["RSI_Signal"] = rsi_sigs
  renko_df["RSI_Type"] = rsi_types
  
  # Unified, noise-filtered signal (EMA9/21/50 alignment + MACD agreement +
  # RSI exhaustion filter + cooldown) — kept for reference / scanners.
  renko_df["Master_Signal"] = compute_master_signal(renko_df, cooldown=signal_cooldown)
  # The literal "blue crosses orange" signal — this is what's actually
  # drawn on the charts now, since it's guaranteed to show every real
  # MACD/Signal-line crossover.
  renko_df["MACD_Cross_Signal"] = compute_macd_line_cross_signal(renko_df, cooldown=1)
  
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
# DATA SOURCE & OUTLOOK
# =====================================================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_live_ohlc(symbol="GC=F", period="6mo", interval="1d"):
  df = yf.download(symbol, period=period, interval=interval, progress=False)
  if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)
  return df
@st.cache_data(ttl=60, show_spinner=False)
def get_live_price_and_chg(symbol):
  try:
    df = yf.download(symbol, period="5d", interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
      df.columns = df.columns.get_level_values(0)
    if df.empty or "Close" not in df.columns:
      return 0.0, 0.0
    closes = df["Close"].dropna()
    if len(closes) < 1:
      return 0.0, 0.0
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) > 1 else last
    chg = ((last - prev) / prev) * 100 if prev else 0.0
    return last, chg
  except Exception:
    return 0.0, 0.0
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
def evaluate_oracle_score(symbol, display=None, macd_fast=12, macd_slow=26, macd_signal=9):
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
    daily = df.resample("1D").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
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
    renko_df, _ = build_atr_renko_df(df, atr_period=21, atr_multiplier=3.0, macd_fast=macd_fast, macd_slow=macd_slow, macd_signal=macd_signal)
    structure_event = latest_structure_event(renko_df, lookback=15)
    structure_label = structure_event["label"] if structure_event else "—"
    structure_type = structure_event["type"] if structure_event else None
    price_fmt = format_price(last_close)
    high_fmt = format_price(high)
    low_fmt = format_price(low)
    return {
        "Ticker": display or symbol,
        "RawSymbol": symbol,
        "Price": f"${price_fmt}",
        "ChangePct": f"{chg:+.2f}%",
        "RawChange": chg,
        "DayHigh": f"${high_fmt}",
        "DayLow": f"${low_fmt}",
        "Signal": sig,
        "Structure": structure_label,
        "StructureType": structure_type,
        "Score": score_str,
        "SL": f"${format_price(sl)}",
        "TP1": f"${format_price(tp1)}",
        "TP1_PCT": f"{tp1_pct:.2f}%",
        "TP2": f"${format_price(tp2)}",
    }
  except Exception:
    return None
def compute_7day_outlook(symbol, display, period="1y", interval="1d", macd_fast=12, macd_slow=26, macd_signal=9):
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
    exp1 = close.ewm(span=macd_fast, adjust=False).mean()
    exp2 = close.ewm(span=macd_slow, adjust=False).mean()
    macd = exp1 - exp2
    macd_signal_line = macd.ewm(span=macd_signal, adjust=False).mean()
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
      bias_score += 1.5
      reasons.append(f"Bullish Trend Alignment: EMA21 (${format_price(last_ema21)}) trades above EMA50 (${format_price(last_ema50)}).")
    else:
      bias_score -= 1.5
      reasons.append(f"Bearish Trend Alignment: EMA21 (${format_price(last_ema21)}) trades below EMA50 (${format_price(last_ema50)}).")
    last_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
    if last_rsi > 55:
      bias_score += 0.5
      reasons.append(f"Momentum Strength: RSI is bullish at {last_rsi:.1f}.")
    elif last_rsi < 45:
      bias_score -= 0.5
      reasons.append(f"Momentum Weakness: RSI is bearish at {last_rsi:.1f}.")
    else:
      reasons.append(f"Neutral Momentum: RSI rests at {last_rsi:.1f}.")
    last_hist = float((macd.iloc[-1] - macd_signal_line.iloc[-1])) if not np.isnan(macd.iloc[-1]) else 0.0
    if last_hist > 0:
      bias_score += 0.5
      reasons.append("MACD Histogram is positive, favoring upward price impulses.")
    else:
      bias_score -= 0.5
      reasons.append("MACD Histogram is negative, favoring downward continuation.")
    renko_df, _ = build_atr_renko_df(
        data,
        atr_period=21,
        atr_multiplier=3.0,
        ema_fast=21,
        ema_slow=50,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal=macd_signal,
        rsi_period=14,
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
        recency = "on latest brick" if bars_ago == 0 else f"{bars_ago} bricks ago"
        if "DEMAND" in s_type:
          reasons.append(f"Smart Money Structure: Bullish {structure_event['label']} at ${format_price(s_level)} ({recency}).")
        else:
          reasons.append(f"Smart Money Structure: Bearish {structure_event['label']} at ${format_price(s_level)} ({recency}).")
    direction = "Bullish" if bias_score >= 1.5 else ("Bearish" if bias_score <= -1.5 else "Neutral/Consolidation")
    weekly_move_pct = atr_pct * np.sqrt(bars_in_7_days)
    tilt = float(np.clip(bias_score / 4.0, -1, 1))
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
# Nifty 500 constituents, sourced from ind_nifty500list.csv.
# Deduplicated below (dict.fromkeys preserves first-seen order) so the
# same ticker never appears twice even if the source CSV is refreshed
# with overlapping/duplicate rows.
_nifty500_csv_raw = [
    "360ONE", "3MINDIA", "ABB", "ACC", "ACMESOLAR", "AIAENG",
    "APLAPOLLO", "AUBANK", "AWL", "AADHARHFC", "AARTIIND", "AAVAS",
    "ABBOTINDIA", "ACE", "ACUTAAS", "ADANIENSOL", "ADANIENT", "ADANIGREEN",
    "ADANIPORTS", "ADANIPOWER", "ATGL", "ABCAPITAL", "ABFRL", "ABLBL",
    "ABREL", "ABSLAMC", "CPPLUS", "AEGISLOG", "AEGISVOPAK", "AFCONS",
    "AFFLE", "AJANTPHARM", "ALKEM", "ABDL", "ARE&M", "AMBER",
    "AMBUJACEM", "ANANDRATHI", "ANANTRAJ", "ANGELONE", "ANTHEM", "ANURAS",
    "APARINDS", "APOLLOHOSP", "APOLLOTYRE", "APTUS", "ASAHIINDIA", "ASHOKLEY",
    "ASIANPAINT", "ASTERDM", "ASTRAL", "ATHERENERG", "ATUL", "AUROPHARMA",
    "AIIL", "DMART", "AXISBANK", "BEML", "BLS", "BSE",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BAJAJHLDNG", "BAJAJHFL", "BALKRISIND",
    "BALRAMCHIN", "BANDHANBNK", "BANKBARODA", "BANKINDIA", "MAHABANK", "BATAINDIA",
    "BAYERCROP", "BELRISE", "BERGEPAINT", "BDL", "BEL", "BHARATFORG",
    "BHEL", "BPCL", "BHARTIARTL", "BHARTIHEXA", "BIKAJI", "GROWW",
    "BIOCON", "BSOFT", "BLUEDART", "BLUEJET", "BLUESTARCO", "BBTC",
    "BOSCHLTD", "FIRSTCRY", "BRIGADE", "BRITANNIA", "MAPMYINDIA", "CCL",
    "CESC", "CGPOWER", "CIEINDIA", "CRISIL", "CANFINHOME", "CANBK",
    "CANHLIFE", "CAPLIPOINT", "CGCL", "CARBORUNIV", "CARTRADE", "CASTROLIND",
    "CEATLTD", "CEMPRO", "CENTRALBK", "CDSL", "CHALET", "CHAMBLFERT",
    "CHENNPETRO", "CHOICEIN", "CHOLAHLDNG", "CHOLAFIN", "CIPLA", "CUB",
    "CLEAN", "COALINDIA", "COCHINSHIP", "COFORGE", "COHANCE", "COLPAL",
    "CAMS", "CONCORDBIO", "CONCOR", "COROMANDEL", "CRAFTSMAN", "CREDITACC",
    "CROMPTON", "CUMMINSIND", "CYIENT", "DCMSHRIRAM", "DLF", "DOMS",
    "DABUR", "DALBHARAT", "DATAPATTNS", "DEEPAKFERT", "DEEPAKNTR", "DELHIVERY",
    "DEVYANI", "DIVISLAB", "DIXON", "LALPATHLAB", "DRREDDY", "DUMMYHEG",
    "EIDPARRY", "EIHOTEL", "EICHERMOT", "ELECON", "ELGIEQUIP", "EMAMILTD",
    "EMCURE", "EMMVEE", "ENDURANCE", "ENGINERSIN", "ERIS", "ESCORTS",
    "ETERNAL", "EXIDEIND", "NYKAA", "FEDERALBNK", "FACT", "FINCABLES",
    "FSL", "FIVESTAR", "FORCEMOT", "FORTIS", "GAIL", "GVT&D",
    "GMRAIRPORT", "GABRIEL", "GALLANTT", "GRSE", "GICRE", "GILLETTE",
    "GLAND", "GLAXO", "GLENMARK", "MEDANTA", "GODIGIT", "GPIL",
    "GODFRYPHLP", "GODREJCP", "GODREJIND", "GODREJPROP", "GRANULES", "GRAPHITE",
    "GRASIM", "GRAVITA", "GESHIP", "FLUOROCHEM", "GMDCLTD", "HEG",
    "HBLENGINE", "HCLTECH", "HDBFS", "HDFCAMC", "HDFCBANK", "HDFCLIFE",
    "HFCL", "HAVELLS", "HEROMOTOCO", "HEXT", "HSCL", "HINDALCO",
    "HAL", "HINDCOPPER", "HINDPETRO", "HINDUNILVR", "HINDZINC", "POWERINDIA",
    "HOMEFIRST", "HONASA", "HONAUT", "HUDCO", "HYUNDAI", "ICICIBANK",
    "ICICIGI", "ICICIAMC", "ICICIPRULI", "IDBI", "IDFCFIRSTB", "IFCI",
    "IIFL", "IRB", "IRCON", "ITCHOTELS", "ITC", "ITI",
    "INDGN", "INDIACEM", "INDIAMART", "INDIANB", "IEX", "INDHOTEL",
    "IOC", "IOB", "IRCTC", "IRFC", "IREDA", "IGL",
    "INDUSTOWER", "INDUSINDBK", "NAUKRI", "INFY", "INOXWIND", "INTELLECT",
    "INDIGO", "IGIL", "IKS", "IPCALAB", "JKCEMENT", "JBMA",
    "JKTYRE", "JMFINANCIL", "JSWCEMENT", "JSWDULUX", "JSWENERGY", "JSWINFRA",
    "JSWSTEEL", "JAINREC", "JPPOWER", "J&KBANK", "JINDALSAW", "JSL",
    "JINDALSTEL", "JIOFIN", "JUBLFOOD", "JUBLINGREA", "JUBLPHARMA", "JWL",
    "JYOTICNC", "KPRMILL", "KEI", "KPITTECH", "KAJARIACER", "KPIL",
    "KALYANKJIL", "KARURVYSYA", "KAYNES", "KEC", "KFINTECH", "KIRLOSENG",
    "KOTAKBANK", "KIMS", "LTF", "LTTS", "LGEINDIA", "LICHSGFIN",
    "LTFOODS", "LTM", "LT", "LATENTVIEW", "LAURUSLABS", "THELEELA",
    "LEMONTREE", "LENSKART", "LICI", "LINDEINDIA", "LLOYDSME", "LODHA",
    "LUPIN", "MMTC", "MRF", "MGL", "M&MFIN", "M&M",
    "MANAPPURAM", "MRPL", "MANKIND", "MARICO", "MARUTI", "MFSL",
    "MAXHEALTH", "MAZDOCK", "MEESHO", "MINDACORP", "MSUMI", "MOTILALOFS",
    "MPHASIS", "MCX", "MUTHOOTFIN", "NATCOPHARM", "NBCC", "NCC",
    "NHPC", "NLCINDIA", "NMDC", "NSLNISP", "NTPCGREEN", "NTPC",
    "NH", "NATIONALUM", "NAVA", "NAVINFLUOR", "NESTLEIND", "NETWEB",
    "NEULANDLAB", "NEWGEN", "NAM-INDIA", "NIVABUPA", "NUVAMA", "NUVOCO",
    "OBEROIRLTY", "ONGC", "OIL", "OLAELEC", "OLECTRA", "PAYTM",
    "ONESOURCE", "OFSS", "POLICYBZR", "PCBL", "PGEL", "PIIND",
    "PNBHOUSING", "PTCIL", "PVRINOX", "PAGEIND", "PARADEEP", "PATANJALI",
    "PERSISTENT", "PETRONET", "PFIZER", "PHOENIXLTD", "PWL", "PIDILITIND",
    "PINELABS", "PIRAMALFIN", "PPLPHARMA", "POLYMED", "POLYCAB", "POONAWALLA",
    "PFC", "POWERGRID", "PREMIERENE", "PRESTIGE", "PFOCUS", "PNB",
    "RRKABEL", "RBLBANK", "RECLTD", "RHIM", "RITES", "RADICO",
    "RVNL", "RAILTEL", "RAINBOW", "RKFORGE", "REDINGTON", "RELIANCE",
    "RPOWER", "SBFC", "SBICARD", "SBILIFE", "SJVN", "SRF",
    "SAGILITY", "SAILIFE", "SAMMAANCAP", "MOTHERSON", "SAPPHIRE", "SARDAEN",
    "SAREGAMA", "SCHAEFFLER", "SCHNEIDER", "SCI", "SHREECEM", "SHRIRAMFIN",
    "SHYAMMETL", "ENRIN", "SIEMENS", "SIGNATURE", "SOBHA", "SOLARINDS",
    "SONACOMS", "SONATSOFTW", "STARHEALTH", "SBIN", "SAIL", "SUMICHEM",
    "SUNPHARMA", "SUNTV", "SUNDARMFIN", "SUPREMEIND", "SPLPETRO", "SUZLON",
    "SWANCORP", "SWIGGY", "SYNGENE", "SYRMA", "TBOTEK", "TVSMOTOR",
    "TATACAP", "TATACHEM", "TATACOMM", "TCS", "TATACONSUM", "TATAELXSI",
    "TATAINVEST", "TMCV", "TMPV", "TATAPOWER", "TATASTEEL", "TATATECH",
    "TTML", "TECHM", "TECHNOE", "TEGA", "TEJASNET", "TENNIND",
    "NIACL", "RAMCOCEM", "THERMAX", "TIMKEN", "TITAGARH", "TITAN",
    "TORNTPHARM", "TORNTPOWER", "TARIL", "TRAVELFOOD", "TRENT", "TRIDENT",
    "TRITURBINE", "TIINDIA", "UCOBANK", "UNOMINDA", "UPL", "UTIAMC",
    "ULTRACEMCO", "UNIONBANK", "UBL", "UNITDSPR", "URBANCO", "USHAMART",
    "VTL", "VBL", "VEDL", "VIJAYA", "VMM", "IDEA",
    "VOLTAS", "WAAREEENER", "WELCORP", "WELSPUNLIV", "WHIRLPOOL", "WIPRO",
    "WOCKPHARMA", "YESBANK", "ZFCVINDIA", "ZEEL", "ZENTEC", "ZENSARTECH",
    "ZYDUSLIFE", "ZYDUSWELL", "ECLERX",
]
nifty500_raw = list(dict.fromkeys(_nifty500_csv_raw))
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
nifty500_yf = [f"{t}.NS" for t in nifty500_raw]
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
    "Nifty500": list(zip(nifty500_yf, nifty500_raw)),
    "US100": list(zip(us100_yf, us100_raw + ["IXIC"])),
}
DISPLAY_TO_SYMBOL = {}
for _cat_symbols in WATCHLIST_CATEGORIES.values():
  for _sym, _disp in _cat_symbols:
    DISPLAY_TO_SYMBOL[_disp] = _sym
VIEWS = ["📊 Charts", "🔎 Scanner"]
TIMEFRAME_PERIODS = {
    "5m": "5d",
    "15m": "10d",
    "30m": "20d",
    "60m": "60d",
    "2h": "60d",
    "4h": "180d",
    "1d": "1y",
    "1wk": "5y",
}
# =====================================================================
# HIGH-CONVICTION DAILY PULLBACK SCAN
# =====================================================================
# Chartink clause replicated here (daily timeframe, cash):
#   close > ema(close,200) and ema(close,9) > ema(close,200)
#   and close > 5 days ago high and close > 10 days ago high
#   and ema(close,9) > ema(close,20) and rsi(14) > 50
#   and low <= ema(close,9) and close > ema(close,9)
#   and volume > sma(volume,20)
# Chartink only covers NSE stocks, so the same clause is evaluated locally on
# Yahoo Finance daily bars — that lets it run on US100, Commodities and Forex too.
CONVICTION_UNIVERSE = {
    "Nifty 500": list(zip(nifty500_yf, nifty500_raw)),
    "US 100": list(zip(us100_yf, us100_raw + ["IXIC"])),
    "Commodities": list(COMMODITIES),
    "Forex": list(FOREX_PAIRS),
}
CONVICTION_CURRENCY = {"Nifty 500": "₹", "US 100": "$", "Commodities": "$", "Forex": ""}
CONVICTION_MAX_DISPLAY = 30
CONVICTION_STATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".qfx_conviction_state.json"
)
def conviction_price_str(cat_name, price):
  cur = CONVICTION_CURRENCY.get(cat_name, "")
  return f"{cur}{format_price(price)}" if cat_name == "Forex" else f"{cur}{price:,.2f}"
def load_conviction_state():
  try:
    if os.path.exists(CONVICTION_STATE_PATH):
      with open(CONVICTION_STATE_PATH, "r") as f:
        data = json.load(f)
      if isinstance(data, dict) and isinstance(data.get("last"), dict):
        return data
  except Exception:
    pass
  return {"last": {}}
def save_conviction_state(state):
  try:
    with open(CONVICTION_STATE_PATH, "w") as f:
      json.dump(state, f)
    return True
  except Exception:
    return False
def _wilder_rsi(close, period=14):
  delta = close.diff()
  gain = delta.clip(lower=0)
  loss = -delta.clip(upper=0)
  avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
  avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
  rs = avg_gain / avg_loss.replace(0, np.nan)
  rsi = 100 - (100 / (1 + rs))
  return rsi.where(avg_loss != 0, 100.0)
def evaluate_conviction_clause(df):
  """Returns None if there isn't enough history, otherwise a dict with
  'passed' (bool) plus the latest price / % change."""
  if df is None or df.empty or not {"Close", "High", "Low"}.issubset(df.columns):
    return None
  df = df.dropna(subset=["Close", "High", "Low"])
  if len(df) < 210:  # EMA200 + the 10-days-ago high need real history
    return None
  close = df["Close"].astype(float)
  high = df["High"].astype(float)
  low = df["Low"].astype(float)
  ema9 = close.ewm(span=9, adjust=False).mean()
  ema20 = close.ewm(span=20, adjust=False).mean()
  ema200 = close.ewm(span=200, adjust=False).mean()
  rsi14 = _wilder_rsi(close, 14)
  c, lo = float(close.iloc[-1]), float(low.iloc[-1])
  e9, e20, e200 = float(ema9.iloc[-1]), float(ema20.iloc[-1]), float(ema200.iloc[-1])
  rsi_now = float(rsi14.iloc[-1]) if pd.notna(rsi14.iloc[-1]) else float("nan")
  # Volume filter — forex pairs (and some indices) report no volume on Yahoo,
  # so the filter is skipped for them instead of rejecting everything.
  vol_ok = True
  if "Volume" in df.columns:
    vol = df["Volume"].astype(float)
    vol_avg = vol.rolling(20).mean().iloc[-1]
    if vol.tail(20).sum() > 0 and pd.notna(vol_avg) and vol_avg > 0:
      vol_ok = float(vol.iloc[-1]) > float(vol_avg)
  passed = bool(
      c > e200
      and e9 > e200
      and c > float(high.iloc[-6])    # "5 days ago high"
      and c > float(high.iloc[-11])   # "10 days ago high"
      and e9 > e20
      and rsi_now > 50
      and lo <= e9
      and c > e9
      and vol_ok
  )
  prev = float(close.iloc[-2])
  chg = ((c - prev) / prev) * 100 if prev else 0.0
  return {"passed": passed, "price": c, "chg": chg, "rsi": rsi_now}
def _frame_for_symbol(data, sym):
  try:
    if isinstance(data.columns, pd.MultiIndex):
      if sym not in data.columns.get_level_values(0):
        return None
      return data[sym]
    return data
  except Exception:
    return None
@st.cache_data(ttl=300, show_spinner=False)
def scan_conviction_category(symbols_tuple):
  """Runs the clause over one watchlist. Returns (hits, n_evaluated).
  n_evaluated == 0 means the data feed failed, so callers must not treat
  an empty hit list as 'nothing matched'."""
  symbols = list(symbols_tuple)
  hits = []
  n_evaluated = 0
  for start in range(0, len(symbols), 100):
    chunk = symbols[start:start + 100]
    tickers = [s for s, _ in chunk]
    try:
      data = yf.download(
          tickers, period="2y", interval="1d", group_by="ticker",
          progress=False, threads=True,
      )
    except Exception:
      continue
    if data is None or data.empty:
      continue
    for sym, disp in chunk:
      try:
        sub = _frame_for_symbol(data, sym)
        res = evaluate_conviction_clause(sub)
        if res is None:
          continue
        n_evaluated += 1
        if res["passed"]:
          hits.append({
              "symbol": sym, "display": disp, "price": res["price"],
              "chg": res["chg"], "rsi": res["rsi"],
          })
      except Exception:
        continue
  hits.sort(key=lambda r: r["chg"], reverse=True)
  return hits, n_evaluated
def get_conviction_results():
  """{category: [hits]} for every watchlist — feeds the right-hand box."""
  return {
      cat: scan_conviction_category(tuple(symbols))[0]
      for cat, symbols in CONVICTION_UNIVERSE.items()
  }
def detect_ema_cross(close_series, fast=9, slow=27, lookback=1):
  """Plain fast-EMA x slow-EMA cross within the last `lookback`+1 bars."""
  if close_series is None or len(close_series) < slow + 3:
    return None
  ef = close_series.ewm(span=int(fast), adjust=False).mean()
  es = close_series.ewm(span=int(slow), adjust=False).mean()
  n = len(close_series)
  for i in range(n - 1, max(n - 1 - lookback, 1) - 1, -1):
    f_now, s_now, f_prev, s_prev = ef.iloc[i], es.iloc[i], ef.iloc[i - 1], es.iloc[i - 1]
    if f_now > s_now and f_prev <= s_prev:
      return {"direction": "BUY", "bars_ago": n - 1 - i}
    if f_now < s_now and f_prev >= s_prev:
      return {"direction": "SELL", "bars_ago": n - 1 - i}
  return None
@st.cache_data(ttl=300, show_spinner=False)
def scan_ema_cross_2h(symbols_tuple, fast=9, slow=27, lookback=1):
  """2H EMA fast/slow cross screener over a whole watchlist (batched download).
  Returns (hits, n_evaluated); hits sorted newest cross first."""
  symbols = list(symbols_tuple)
  hits, n_evaluated = [], 0
  agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
  for start in range(0, len(symbols), 100):
    chunk = symbols[start:start + 100]
    try:
      data = yf.download([t for t, _ in chunk], period="60d", interval="60m",
                         group_by="ticker", progress=False, threads=True)
    except Exception:
      continue
    if data is None or data.empty:
      continue
    for sym, disp in chunk:
      try:
        sub = _frame_for_symbol(data, sym)
        if sub is None:
          continue
        sub = sub.dropna(subset=["Close"])
        if sub.empty:
          continue
        d2 = sub.resample("2h").agg({k: v for k, v in agg.items() if k in sub.columns}).dropna(subset=["Close"])
        if len(d2) < int(slow) + 3:
          continue
        n_evaluated += 1
        cross = detect_ema_cross(d2["Close"], fast=fast, slow=slow, lookback=lookback)
        if not cross:
          continue
        last = float(d2["Close"].iloc[-1])
        prev = float(d2["Close"].iloc[-2])
        hits.append({
            "symbol": sym, "display": disp, "price": last,
            "chg": ((last - prev) / prev * 100) if prev else 0.0,
            "direction": cross["direction"], "bars_ago": cross["bars_ago"],
        })
      except Exception:
        continue
  hits.sort(key=lambda r: (r["bars_ago"], r["direction"] != "BUY", -abs(r["chg"])))
  return hits, n_evaluated
# =====================================================================
# CHARTING
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
    size=9,
    absolute_offset=None,
    button_style=False,
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
  # "button_style" renders larger, bolder, rounded-feel badges (like the
  # red/green SELL/BUY pills used on the MACD panel) instead of the thin
  # inline tags used elsewhere.
  btn_pad = 6 if button_style else 2
  btn_border = 2 if button_style else 1
  btn_font_size = size + 2 if button_style else size
  for i in range(len(signal_arr)):
    sig = signal_arr[i]
    if sig == "BUY":
      fig.add_annotation(
          x=x_arr[i],
          y=buy_y_arr[i],
          text="<b>BUY</b>",
          showarrow=False,
          font=dict(color="#0B0E11", size=btn_font_size),
          bgcolor=COLOR_GREEN,
          bordercolor=COLOR_GREEN,
          borderwidth=btn_border,
          borderpad=btn_pad,
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
          font=dict(color="#FFFFFF", size=btn_font_size),
          bgcolor=COLOR_RED,
          bordercolor=COLOR_RED,
          borderwidth=btn_border,
          borderpad=btn_pad,
          opacity=0.95,
          yanchor="bottom",
          row=row,
          col=col,
      )
COLOR_HA_UP = COLOR_BULL    # Heikin Ashi candles use the Renko brick colours
COLOR_HA_DOWN = COLOR_BEAR
COLOR_PILL_BUY = "#4E9E90"
COLOR_PILL_SELL = "#D0827E"
# TradingView-style 4-colour MACD histogram
COLOR_HIST_POS_UP = "#26A69A"
COLOR_HIST_POS_DOWN = "#B2DFDB"
COLOR_HIST_NEG_DOWN = "#FF5252"
COLOR_HIST_NEG_UP = "#FFCDD2"
def compute_independent_macd(close, fast=12, slow=26, signal=9, smooth=3):
  """MACD computed straight from the real candles of the selected timeframe —
  no Renko / Heikin Ashi involved. BUY = MACD line crosses above the signal
  line, SELL = crosses below."""
  close = pd.Series(close, dtype=float).reset_index(drop=True)
  raw = close.ewm(span=int(fast), adjust=False).mean() - close.ewm(span=int(slow), adjust=False).mean()
  macd = raw.ewm(span=int(smooth), adjust=False).mean() if smooth and int(smooth) > 1 else raw
  sig = macd.ewm(span=int(signal), adjust=False).mean()
  hist = macd - sig
  cross = ["HOLD"] * len(close)
  m, sg = macd.values, sig.values
  for i in range(max(int(slow), 1), len(close)):
    if not (np.isfinite(m[i]) and np.isfinite(sg[i]) and np.isfinite(m[i - 1]) and np.isfinite(sg[i - 1])):
      continue
    if m[i] > sg[i] and m[i - 1] <= sg[i - 1]:
      cross[i] = "BUY"
    elif m[i] < sg[i] and m[i - 1] >= sg[i - 1]:
      cross[i] = "SELL"
  return pd.DataFrame({"MACD": macd, "Signal": sig, "Hist": hist, "Cross": cross})
def add_pill_signals(fig, x_vals, signals, y_buy, y_sell, row, size=11):
  """Muted 'Buy' / 'Sell' pills (TradingView look)."""
  x_arr = np.asarray(x_vals)
  sig_arr = np.asarray(signals)
  yb = np.asarray(y_buy, dtype=float)
  ys = np.asarray(y_sell, dtype=float)
  for i in range(len(sig_arr)):
    if sig_arr[i] == "BUY" and np.isfinite(yb[i]):
      fig.add_annotation(
          x=x_arr[i], y=yb[i], text="Buy", showarrow=False,
          font=dict(color="#FFFFFF", size=size), bgcolor=COLOR_PILL_BUY,
          bordercolor=COLOR_PILL_BUY, borderwidth=1, borderpad=4, opacity=0.95,
          yanchor="top", row=row, col=1,
      )
    elif sig_arr[i] == "SELL" and np.isfinite(ys[i]):
      fig.add_annotation(
          x=x_arr[i], y=ys[i], text="Sell", showarrow=False,
          font=dict(color="#FFFFFF", size=size), bgcolor=COLOR_PILL_SELL,
          bordercolor=COLOR_PILL_SELL, borderwidth=1, borderpad=4, opacity=0.95,
          yanchor="bottom", row=row, col=1,
      )
def _date_ticks(dates, n_ticks=10):
  n = len(dates)
  if n == 0:
    return [], []
  idxs = np.linspace(0, n - 1, min(n_ticks, n), dtype=int)
  vals, texts = [], []
  for i in idxs:
    dt = dates[i]
    vals.append(int(i))
    if hasattr(dt, "strftime"):
      texts.append(dt.strftime("%d-%m %H:%M" if (dt.hour != 0 or dt.minute != 0) else "%d-%m"))
    else:
      texts.append(str(dt))
  return vals, texts
STRUCT_NAMES = {
    "BOS_DEMAND": "BOS Demand", "BOS_SUPPLY": "BOS Supply",
    "CHOCH_DEMAND": "CHoCH Demand", "CHOCH_SUPPLY": "CHoCH Supply",
}
def create_chart_figure(
    renko_df, ha_df, brick_size, display, ema_fast, ema_slow, ema_mid=None,
    live_price=None, live_chg=None, symbol_label=None, raw_df=None, macd_params=None,
):
  """Rows: 1) real Heikin Ashi (built from the actual candles)
           2) ATR Renko
           3) MACD (independent, from the actual candles)
           4) RSI (Renko bricks)
  Rows 1+3 share the real-candle time axis; rows 2+4 share the brick axis.
  Both groups are kept on the same time window when zooming / panning (see the
  zoom-sync map below and qfxLinkAxes in render_zoomable_chart)."""
  macd_params = macd_params or {}
  n_ha = len(ha_df)
  x_ha = list(range(n_ha))
  ha_dates = list(raw_df.index) if raw_df is not None and len(raw_df) == n_ha else []
  ha_tick_vals, ha_tick_texts = _date_ticks(ha_dates)
  x_renko = list(range(len(renko_df)))
  if "Date" in renko_df.columns and len(renko_df) > 0:
    rk_tick_vals, rk_tick_texts = _date_ticks(list(renko_df["Date"]))
  else:
    rk_tick_vals, rk_tick_texts = [], []
  # Renko / RSI signal: Buy when EMA fast crosses above EMA mid (9 x 27), Sell when below.
  _rf = renko_df["EMA_FAST"].astype(float).values
  _rm = (renko_df["EMA_MID"] if "EMA_MID" in renko_df.columns else renko_df["EMA_SLOW"]).astype(float).values
  _sig = ["HOLD"] * len(renko_df)
  for _i in range(1, len(renko_df)):
    if np.isfinite(_rf[_i]) and np.isfinite(_rm[_i]) and np.isfinite(_rf[_i - 1]) and np.isfinite(_rm[_i - 1]):
      if _rf[_i] > _rm[_i] and _rf[_i - 1] <= _rm[_i - 1]:
        _sig[_i] = "BUY"
      elif _rf[_i] < _rm[_i] and _rf[_i - 1] >= _rm[_i - 1]:
        _sig[_i] = "SELL"
  master_signal = pd.Series(_sig)
  macd_df = compute_independent_macd(
      ha_df["Close"] if raw_df is None else raw_df["Close"],
      fast=macd_params.get("fast", 12), slow=macd_params.get("slow", 26),
      signal=macd_params.get("signal", 9), smooth=macd_params.get("smooth", 3),
  )
  fig = make_subplots(
      rows=4, cols=1, shared_xaxes=False,
      row_heights=[0.34, 0.30, 0.16, 0.20],
      vertical_spacing=0.035,
      subplot_titles=(
          f"{display} — Heikin Ashi (EMA {ema_fast}/{ema_mid or ema_slow})",
          f"{display} — ATR Renko (Buy/Sell = EMA {ema_fast} × {ema_mid or ema_slow} cross)",
          f"MACD {macd_params.get('fast', 12)}/{macd_params.get('slow', 26)}/{macd_params.get('signal', 9)} — independent Buy/Sell (MACD × Signal)",
          f"RSI (Buy/Sell = Renko EMA {ema_fast} × {ema_mid or ema_slow} cross • Green 30 / Red 70 levels)",
      ),
  )
  # ---------------- Row 1: real Heikin Ashi -----------------------------
  ha_close = ha_df["Close"].astype(float)
  fast_s = ha_df["EMA_FAST"].astype(float)
  slow_s = ha_df["EMA_SLOW"].astype(float)
  mid_s = ha_df["EMA_MID"].astype(float) if (ema_mid is not None and "EMA_MID" in ha_df.columns) else slow_s
  # Bollinger-style dashed bands
  bb_mid = ha_close.rolling(20).mean()
  bb_std = ha_close.rolling(20).std()
  fig.add_trace(go.Scatter(x=x_ha, y=bb_mid + 2 * bb_std, mode="lines", hoverinfo="skip",
                           line=dict(color=COLOR_HA_UP, width=1, dash="dash"), opacity=0.7, showlegend=False), row=1, col=1)
  fig.add_trace(go.Scatter(x=x_ha, y=bb_mid - 2 * bb_std, mode="lines", hoverinfo="skip",
                           line=dict(color="#FF5252", width=1, dash="dash"), opacity=0.7, showlegend=False), row=1, col=1)
  # (EMA ribbon colour fill removed - only the three EMA lines below are drawn)
  f_arr, m_arr = fast_s.values, mid_s.values
  fig.add_trace(
      go.Candlestick(
          x=x_ha, open=ha_df["Open"], high=ha_df["High"], low=ha_df["Low"], close=ha_df["Close"],
          increasing_line_color=COLOR_HA_UP, decreasing_line_color=COLOR_HA_DOWN,
          increasing_fillcolor=COLOR_HA_UP, decreasing_fillcolor=COLOR_HA_DOWN,
          name="Heikin Ashi", showlegend=False,
      ), row=1, col=1,
  )
  fig.add_trace(go.Scatter(x=x_ha, y=fast_s, line=dict(color="#FFFFFF", width=1.2), name=f"HA EMA {ema_fast}", showlegend=False), row=1, col=1)
  if mid_s is not slow_s:
    fig.add_trace(go.Scatter(x=x_ha, y=mid_s, line=dict(color="#F0456F", width=1.2), name=f"HA EMA {ema_mid}", showlegend=False), row=1, col=1)
  fig.add_trace(go.Scatter(x=x_ha, y=slow_s, line=dict(color="#9FA8C3", width=1.2), name=f"HA EMA {ema_slow}", showlegend=False), row=1, col=1)
  # Ribbon-cross Buy/Sell on the Heikin Ashi candles
  ha_sig = ["HOLD"] * n_ha
  for i in range(1, n_ha):
    if np.isfinite(f_arr[i]) and np.isfinite(m_arr[i]) and np.isfinite(f_arr[i - 1]) and np.isfinite(m_arr[i - 1]):
      if f_arr[i] > m_arr[i] and f_arr[i - 1] <= m_arr[i - 1]:
        ha_sig[i] = "BUY"
      elif f_arr[i] < m_arr[i] and f_arr[i - 1] >= m_arr[i - 1]:
        ha_sig[i] = "SELL"
  ha_rng = float(np.nanmax(ha_df["High"].values) - np.nanmin(ha_df["Low"].values)) if n_ha else 0.0
  ha_pad = ha_rng * 0.02
  add_pill_signals(fig, x_ha, ha_sig, ha_df["Low"].values - ha_pad, ha_df["High"].values + ha_pad, row=1)
  if raw_df is not None and n_ha:
    last_close = float(raw_df["Close"].iloc[-1])
    fig.add_hline(y=last_close, line=dict(color=COLOR_HA_UP, width=1, dash="dot"), row=1, col=1)
    # Market-structure label (BOS / CHoCH) computed on the real candles
    try:
      st_df = detect_market_structure(raw_df["High"], raw_df["Low"], raw_df["Close"], swing_lookback=5)
      ev = latest_structure_event(st_df, lookback=len(st_df))
      if ev is not None and ev["type"] in STRUCT_NAMES:
        i_ev = n_ha - 1 - ev["bars_ago"]
        origin = st_df["StructureOriginIdx"].iloc[i_ev]
        x0 = int(origin) if pd.notna(origin) else max(i_ev - 6, 0)
        is_up = ev["type"] in ("BOS_DEMAND", "CHOCH_DEMAND")
        color = COLOR_BOS_DEMAND if is_up else COLOR_BOS_SUPPLY
        fig.add_shape(type="line", x0=x0, x1=n_ha - 1, y0=ev["level"], y1=ev["level"],
                      line=dict(color=color, width=1.2, dash="dash"), opacity=0.6, row=1, col=1)
        seq = st_df["StructureSeq"].iloc[i_ev]
        seq_txt = f" ({int(seq)})" if pd.notna(seq) else ""
        fig.add_annotation(
            x=i_ev, y=ev["level"], text=f"{STRUCT_NAMES[ev['type']]}{seq_txt}", showarrow=False,
            font=dict(color="#FFFFFF", size=10), bgcolor="#4A4F5C", bordercolor="#4A4F5C",
            borderwidth=1, borderpad=4, opacity=0.95, yshift=-16 if is_up else 16, row=1, col=1,
        )
    except Exception:
      pass
  # ---------------- Row 2: ATR Renko -------------------------------------
  fig.add_trace(
      go.Candlestick(
          x=x_renko, open=renko_df["Open"], high=renko_df["High"], low=renko_df["Low"], close=renko_df["Close"],
          increasing_line_color=COLOR_BULL, decreasing_line_color=COLOR_BEAR,
          increasing_fillcolor=COLOR_BULL, decreasing_fillcolor=COLOR_BEAR,
          name="ATR Renko", showlegend=False,
      ), row=2, col=1,
  )
  fig.add_trace(go.Scatter(x=x_renko, y=renko_df["EMA_FAST"], line=dict(color=COLOR_MA_FAST, width=1.5), name=f"EMA {ema_fast}", showlegend=False), row=2, col=1)
  fig.add_trace(go.Scatter(x=x_renko, y=renko_df["EMA_SLOW"], line=dict(color=COLOR_MA_SLOW, width=1.5), name=f"EMA {ema_slow}", showlegend=False), row=2, col=1)
  if ema_mid is not None and "EMA_MID" in renko_df.columns:
    fig.add_trace(go.Scatter(x=x_renko, y=renko_df["EMA_MID"], line=dict(color="#FFFFFF", width=1.3), name=f"EMA {ema_mid}", showlegend=False), row=2, col=1)
  _rk_pad = float(np.nanmax(renko_df["High"].values) - np.nanmin(renko_df["Low"].values)) * 0.02 if len(renko_df) else 0.0
  add_pill_signals(fig, x_renko, master_signal, renko_df["Low"].values - _rk_pad, renko_df["High"].values + _rk_pad, row=2)
  struct_style = {
      "BOS_DEMAND": (COLOR_BOS_DEMAND, "B-S"),
      "BOS_SUPPLY": (COLOR_BOS_SUPPLY, "B-D"),
      "CHOCH_DEMAND": (COLOR_CHOCH_DEMAND, "CH-S"),
      "CHOCH_SUPPLY": (COLOR_CHOCH_SUPPLY, "CH-D"),
  }
  last_struct_event = latest_structure_event(renko_df, lookback=len(renko_df))
  if last_struct_event is not None:
    s_type = last_struct_event["type"]
    if s_type in struct_style:
      color, label = struct_style[s_type]
      s_level = last_struct_event["level"]
      i = len(renko_df) - 1 - last_struct_event["bars_ago"]
      origin_idx = renko_df["StructureOriginIdx"].iloc[i]
      span_start = int(origin_idx) if pd.notna(origin_idx) else max(i - 6, 0)
      fig.add_shape(type="line", x0=span_start, x1=len(renko_df) - 1, y0=s_level, y1=s_level,
                    line=dict(color=color, width=1.5, dash="dash"), opacity=0.6, row=2, col=1)
      fig.add_annotation(x=i, y=s_level, text=label, showarrow=False,
                         font=dict(color="#FFFFFF", size=10), bgcolor="#1E222D", bordercolor=color,
                         borderwidth=1, row=2, col=1,
                         yshift=14 if s_type in ("BOS_DEMAND", "CHOCH_DEMAND") else -14)
  # ---------------- Row 3: independent MACD (TradingView style) ---------
  hist = macd_df["Hist"].values.astype(float)
  prev_hist = np.r_[np.nan, hist[:-1]]
  hist_colors = []
  for h, p in zip(hist, prev_hist):
    rising = (not np.isfinite(p)) or h >= p
    if h >= 0:
      hist_colors.append(COLOR_HIST_POS_UP if rising else COLOR_HIST_POS_DOWN)
    else:
      hist_colors.append(COLOR_HIST_NEG_UP if rising else COLOR_HIST_NEG_DOWN)
  fig.add_trace(go.Bar(x=x_ha, y=hist, marker_color=hist_colors, marker_line_color=COLOR_BG_DARK, marker_line_width=1,
                       name="Histogram", showlegend=False), row=3, col=1)
  fig.add_trace(go.Scatter(x=x_ha, y=macd_df["MACD"], line=dict(color=COLOR_MACD_LINE, width=1.3),
                           name="MACD", showlegend=False), row=3, col=1)
  fig.add_trace(go.Scatter(x=x_ha, y=macd_df["Signal"], line=dict(color=COLOR_SIGNAL_LINE, width=1.3),
                           name="Signal", showlegend=False), row=3, col=1)
  fig.add_hline(y=0, line=dict(color="#787B86", width=1, dash="dot"), row=3, col=1)
  m_vals = macd_df["MACD"].values.astype(float)
  s_vals = macd_df["Signal"].values.astype(float)
  finite = np.concatenate([m_vals[np.isfinite(m_vals)], s_vals[np.isfinite(s_vals)], hist[np.isfinite(hist)]])
  m_pad = (finite.max() - finite.min()) * 0.10 if finite.size else 0.001
  lo_line = np.minimum(np.minimum(m_vals, s_vals), hist)
  hi_line = np.maximum(np.maximum(m_vals, s_vals), hist)
  add_pill_signals(fig, x_ha, macd_df["Cross"].values, lo_line - m_pad, hi_line + m_pad, row=3)
  # ---------------- Row 4: RSI (Renko bricks) ----------------------------
  rsi_vals = renko_df["RSI"].values
  fig.add_trace(go.Scatter(x=x_renko, y=rsi_vals, line=dict(color="#00D4FF", width=1.8), name="RSI", showlegend=False), row=4, col=1)
  fig.add_hline(y=70, line=dict(color=COLOR_RED, width=1, dash="dash"), row=4, col=1)
  fig.add_hline(y=30, line=dict(color=COLOR_GREEN, width=1, dash="dash"), row=4, col=1)
  fig.update_yaxes(range=[0, 100], row=4, col=1)
  add_buy_sell_markers(fig, x_renko, master_signal, renko_df["RSI"], renko_df["RSI"], row=4, col=1, absolute_offset=12.0)
  # ---------------- Zoom-sync map (Renko bricks <-> real candles) --------
  # Bricks are not time based, so bricks and candles cannot share one x axis.
  # Every brick is given a position on the real-candle axis (the candle it formed
  # on; several bricks from one candle are spread inside that candle's slot).
  # The table travels with the figure (layout.meta) and render_zoomable_chart uses
  # it to keep every panel on the same time window while zooming / panning.
  n_rk = len(renko_df)
  brick_pos = None
  if n_ha > 1 and n_rk > 1:
    try:
      if ha_dates and "Date" in renko_df.columns:
        c_dates = pd.DatetimeIndex(ha_dates)
        if c_dates.is_monotonic_increasing:
          c_idx = np.clip(c_dates.searchsorted(pd.DatetimeIndex(renko_df["Date"]), side="right") - 1, 0, n_ha - 1)
          c_ser = pd.Series(c_idx)
          k_in = c_ser.groupby(c_ser).cumcount().values
          m_in = c_ser.groupby(c_ser).transform("size").values
          brick_pos = c_idx - 0.5 + (k_in + 0.5) / m_in
    except Exception:
      brick_pos = None
    if brick_pos is None:
      brick_pos = np.linspace(0, n_ha - 1, n_rk)   # no usable dates: sync by relative position
    if np.all(np.diff(brick_pos) > 0):
      fig.update_layout(meta=dict(qfx_sync=dict(
          brick_pos=[round(float(v), 6) for v in brick_pos], n_candles=int(n_ha))))
  # ---------------- Watermark + layout -----------------------------------
  ticker_label = (symbol_label or display or "").strip()
  if live_price is not None:
    price_txt = f"${format_price(live_price)}"
    if live_chg is not None:
      arrow = "▲" if live_chg >= 0 else "▼"
      price_txt += f"  {arrow} {live_chg:+.2f}%"
    price_color = COLOR_GREEN if (live_chg or 0) >= 0 else COLOR_RED
  else:
    price_txt = ""
    price_color = COLOR_TEXT_MAIN
  vertical_text = f"{ticker_label}   {price_txt}".strip()
  fig.add_annotation(
      xref="paper", yref="paper", x=-0.045, y=0.5,
      text=f"<b>{ticker_label}</b>  <span style='color:{price_color}'>{price_txt}</span>" if vertical_text else "",
      showarrow=False, textangle=-90, font=dict(color=COLOR_TEXT_MAIN, size=13),
      xanchor="center", yanchor="middle",
  )
  fig.update_layout(
      height=950, paper_bgcolor=COLOR_BG_DARK, plot_bgcolor=COLOR_BG_DARK,
      font=dict(color=COLOR_TEXT_MUTED, size=10), showlegend=False,
      margin=dict(l=48, r=70, t=40, b=10), bargap=0.45,
      dragmode="pan",
  )
  fig.update_xaxes(rangeslider_visible=False, showgrid=False, tickfont=dict(size=10))
  # Heikin Ashi (x) + MACD (x3) share the real-candle axis; Renko (x2) + RSI (x4) share
  # the brick axis. qfxLinkAxes() (render_zoomable_chart) locks the two groups to the
  # same time window, so all four panels zoom / pan / reset together.
  fig.update_xaxes(showticklabels=False, row=1, col=1)
  fig.update_xaxes(showticklabels=False, row=2, col=1)
  fig.update_xaxes(matches="x", row=3, col=1, showticklabels=bool(ha_tick_vals),
                   tickvals=ha_tick_vals or None, ticktext=ha_tick_texts or None)
  fig.update_xaxes(matches="x2", row=4, col=1, showticklabels=bool(rk_tick_vals),
                   tickvals=rk_tick_vals or None, ticktext=rk_tick_texts or None)
  for r in range(1, 4):
    fig.update_yaxes(gridcolor="#2A2F3A", side="right", row=r, col=1, tickformat="f",
                     hoverformat="f", tickfont=dict(size=10), automargin=True,
                     ticklabelposition="outside right")
  return fig
def go_to_chart(symbol, display):
  st.session_state.chart_symbol = symbol
  st.session_state.chart_display = display
  st.session_state.active_view = VIEWS[0]
def run_chart_search():
  query = (st.session_state.get("chart_search_box") or "").strip()
  if not query:
    return
  q_upper = query.upper()
  if q_upper in DISPLAY_TO_SYMBOL:
    go_to_chart(DISPLAY_TO_SYMBOL[q_upper], q_upper)
    return
  for disp, sym in DISPLAY_TO_SYMBOL.items():
    if sym.upper() == q_upper:
      go_to_chart(sym, disp)
      return
  go_to_chart(query, query)
QFX_SYNC_JS = r"""
// ---------------------------------------------------------------------------------
// qfxLinkAxes - ONE controller that keeps every panel (Heikin Ashi, Renko, MACD, RSI)
// moving together:
//   * pan left / right / up / down            -> all four panels move
//   * zoom in / out (wheel, box, axis drag, +/- buttons, touch pinch) -> all four zoom
//   * reset / autoscale                       -> all four reset
// X axis: Heikin Ashi + MACD use the real-candle axis, Renko + RSI use the brick axis.
//         The brick -> candle table in layout.meta.qfx_sync converts between the two.
// Y axis: every panel has its own scale (price / MACD / RSI), so a vertical move or a
//         vertical zoom is copied as the same FRACTION of each panel's starting range.
// Touch:  1 finger = pan, 2 fingers = pinch zoom. Plotly's own touch drag is switched
//         off (capture-phase listeners) so it cannot fight with this handler.
// ---------------------------------------------------------------------------------
function qfxLinkAxes(el, spec) {
  var PANELS = [
    {xa: "xaxis",  ya: "yaxis",  g: "c"},   // Heikin Ashi (real candles)
    {xa: "xaxis2", ya: "yaxis2", g: "b"},   // ATR Renko   (bricks)
    {xa: "xaxis3", ya: "yaxis3", g: "c"},   // MACD        (real candles)
    {xa: "xaxis4", ya: "yaxis4", g: "b"}    // RSI         (bricks)
  ];
  var api = {reset: function () {}, toggleTouch: function () { return "chart"; }};
  var L0 = el._fullLayout;
  if (!L0 || !L0.yaxis4 || !L0.xaxis4) { return api; }
  // ---- brick <-> candle x mapping --------------------------------------------------
  var meta = spec && spec.layout && spec.layout.meta;
  var sync = meta && meta.qfx_sync;
  var P = (sync && sync.brick_pos && sync.brick_pos.length > 1) ? sync.brick_pos : null;
  var nB = P ? P.length : 0;
  var perCandle = P ? (nB - 1) / Math.max(P[nB - 1] - P[0], 1e-9) : 1;   // bricks per candle
  function candleToBrick(x) {
    if (!P) { return x; }
    if (x <= P[0]) { return (x - P[0]) * perCandle; }
    if (x >= P[nB - 1]) { return (nB - 1) + (x - P[nB - 1]) * perCandle; }
    var lo = 0, hi = nB - 1;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (P[mid] <= x) { lo = mid; } else { hi = mid; } }
    return lo + (x - P[lo]) / (P[lo + 1] - P[lo]);
  }
  function brickToCandle(b) {
    if (!P) { return b; }
    if (b <= 0) { return P[0] + b / perCandle; }
    if (b >= nB - 1) { return P[nB - 1] + (b - (nB - 1)) / perCandle; }
    var j = Math.floor(b);
    return P[j] + (b - j) * (P[j + 1] - P[j]);
  }
  // ---- starting y ranges (used to copy vertical moves / zooms between panels) -------
  var Y0 = {};
  PANELS.forEach(function (p) {
    var r = el._fullLayout[p.ya].range;
    Y0[p.ya] = [r[0], r[1]];
  });
  function yFrom(fromIdx, toIdx, r) {
    var s = Y0[PANELS[fromIdx].ya], d = Y0[PANELS[toIdx].ya];
    var span = s[1] - s[0];
    if (!span) { return [d[0], d[1]]; }
    var f0 = (r[0] - s[0]) / span, f1 = (r[1] - s[0]) / span, dspan = d[1] - d[0];
    return [d[0] + f0 * dspan, d[0] + f1 * dspan];
  }
  // ---- build one relayout update that moves every other panel ------------------------
  // xs / ys = index of the panel the move came from (-1 = none); xr / yr = its new range.
  // withSource = also write the source panel itself (needed for touch, not for Plotly's own drag).
  function buildUpdate(xs, xr, ys, yr, withSource) {
    var upd = {};
    if (xs >= 0 && xr) {
      var sg = PANELS[xs].g;
      var lo = Math.min(xr[0], xr[1]), hi = Math.max(xr[0], xr[1]);
      var conv = (sg === "c") ? [candleToBrick(lo), candleToBrick(hi)] : [brickToCandle(lo), brickToCandle(hi)];
      PANELS.forEach(function (p) {
        if (p.g !== sg) { upd[p.xa + ".range"] = conv.slice(); }
        else if (withSource) { upd[p.xa + ".range"] = [xr[0], xr[1]]; }
      });
    }
    if (ys >= 0 && yr) {
      PANELS.forEach(function (p, i) {
        if (i !== ys) { upd[p.ya + ".range"] = yFrom(ys, i, yr); }
        else if (withSource) { upd[p.ya + ".range"] = [yr[0], yr[1]]; }
      });
    }
    return upd;
  }
  function sameRange(a, b) {
    var tol = 1e-9 * (Math.abs(a[1] - a[0]) + 1);
    return Math.abs(a[0] - b[0]) <= tol && Math.abs(a[1] - b[1]) <= tol;
  }
  function prune(upd) {          // drop axes that are already there; null when nothing is left
    var L = el._fullLayout, n = 0;
    Object.keys(upd).forEach(function (k) {
      var ax = L[k.replace(".range", "")];
      if (ax && ax.range && !ax.autorange && sameRange(ax.range, upd[k])) { delete upd[k]; } else { n++; }
    });
    return n ? upd : null;
  }
  function resetUpdate() {
    var upd = {};
    PANELS.forEach(function (p) {
      upd[p.xa + ".autorange"] = true;
      upd[p.ya + ".range"] = [Y0[p.ya][0], Y0[p.ya][1]];
    });
    return upd;
  }
  // ---- apply updates (one relayout per animation frame, newest wins) -------------------
  var busy = false, pending = null, running = false, deferred = null, replays = 0;
  function done() {
    busy = false;
    if (pending) { requestAnimationFrame(flush); return; }
    running = false;
    if (deferred && replays < 2) {         // a Plotly event arrived while we were busy: re-check once
      var d = deferred; deferred = null; replays++;
      onNative(d, true);
    } else { deferred = null; }
  }
  function flush() {
    var u = pending; pending = null;
    if (!u) { running = false; return; }
    busy = true;
    var pr;
    try { pr = Plotly.relayout(el, u); } catch (err) { done(); return; }
    pr.then(done, done);
  }
  function schedule(u) {
    if (!u) { return; }
    pending = u;
    if (!running) { running = true; requestAnimationFrame(flush); }
  }
  // ---- Plotly's own pan / zoom / reset (mouse, wheel, modebar, axis drag) --------------
  function axRange(ev, name) {
    var a = ev[name + ".range[0]"], b = ev[name + ".range[1]"], r = ev[name + ".range"];
    if (a !== undefined && b !== undefined) { return [a, b]; }
    if (r && r.length === 2) { return [r[0], r[1]]; }
    var ax = el._fullLayout[name];
    return (ax && ax.range) ? [ax.range[0], ax.range[1]] : null;
  }
  function parseAxes(ev) {
    var out = {xi: -1, yi: -1, reset: false};
    Object.keys(ev).forEach(function (k) {
      var m = /^([xy])axis(\d*)\.(range|autorange)/.exec(k);
      if (!m) { return; }
      var i = (m[2] ? parseInt(m[2], 10) : 1) - 1;
      if (i < 0 || i >= PANELS.length) { return; }
      if (m[3] === "autorange") { if (ev[k] === true) { out.reset = true; } return; }
      if (m[1] === "x") { if (out.xi < 0) { out.xi = i; } } else if (out.yi < 0) { out.yi = i; }
    });
    return out;
  }
  function onNative(ev, isReplay) {
    if (!ev) { return; }
    if (busy) { deferred = ev; return; }
    if (!isReplay) { replays = 0; }
    var a = parseAxes(ev);
    if (a.reset) { if (!isReplay) { schedule(resetUpdate()); } return; }
    if (a.xi < 0 && a.yi < 0) { return; }
    var xr = a.xi >= 0 ? axRange(ev, PANELS[a.xi].xa) : null;
    var yr = a.yi >= 0 ? axRange(ev, PANELS[a.yi].ya) : null;
    schedule(prune(buildUpdate(a.xi, xr, a.yi, yr, false)));
  }
  el.on("plotly_relayout", function (ev) { onNative(ev, false); });
  el.on("plotly_relayouting", function (ev) { onNative(ev, false); });   // live, while dragging
  // ---- touch: 1 finger = pan (left/right/up/down), 2 fingers = pinch zoom -------------
  var mode = "chart", G = null;
  el.style.touchAction = "none";
  function pt(t) {
    var r = el.getBoundingClientRect();
    return [t.clientX - r.left, t.clientY - r.top];
  }
  function describe(touches) {
    var a = pt(touches[0]), b = touches.length > 1 ? pt(touches[1]) : null;
    return {
      n: b ? 2 : 1,
      mid: b ? [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] : a,
      dist: b ? Math.sqrt(Math.pow(a[0] - b[0], 2) + Math.pow(a[1] - b[1], 2)) : 0
    };
  }
  function panelAt(y) {           // panel whose plot area is closest (vertically) to y
    var best = 0, bd = 1e12, L = el._fullLayout;
    PANELS.forEach(function (p, i) {
      var ya = L[p.ya];
      if (!ya) { return; }
      var top = ya._offset, bot = ya._offset + ya._length;
      var d = y < top ? top - y : (y > bot ? y - bot : 0);
      if (d < bd) { bd = d; best = i; }
    });
    return best;
  }
  function begin(touches) {       // remember the start of a gesture (re-called when a finger is added / lifted)
    var d = describe(touches), L = el._fullLayout, i = panelAt(d.mid[1]), p = PANELS[i];
    var xa = L[p.xa], ya = L[p.ya];
    if (!xa || !ya || !xa.range || !ya.range || !(xa._length > 0) || !(ya._length > 0)) { return null; }
    return {
      n: d.n, mid: d.mid, dist: d.dist, i: i,
      xr: [xa.range[0], xa.range[1]], yr: [ya.range[0], ya.range[1]],
      xo: xa._offset, xl: xa._length, yo: ya._offset, yl: ya._length
    };
  }
  function moveGesture(touches) {
    var d = describe(touches), s = 1;
    if (G.n === 2 && d.n === 2 && G.dist > 10 && d.dist > 10) { s = G.dist / d.dist; }   // fingers apart -> s < 1 -> zoom in
    var xs0 = G.xr[1] - G.xr[0], ys0 = G.yr[1] - G.yr[0];
    s = Math.min(20, Math.max(s, 0.05));
    if (s < 1 && xs0 * s < 3) { s = Math.min(1, 3 / xs0); }     // never fewer than ~3 candles / bricks
    var xs = xs0 * s, ys = ys0 * s;
    var fx = G.xr[0] + (G.mid[0] - G.xo) / G.xl * xs0;            // data point that was under the fingers
    var x0 = fx - (d.mid[0] - G.xo) / G.xl * xs;
    var fy = G.yr[1] - (G.mid[1] - G.yo) / G.yl * ys0;
    var y1 = fy + (d.mid[1] - G.yo) / G.yl * ys;
    schedule(prune(buildUpdate(G.i, [x0, x0 + xs], G.i, [y1 - ys, y1], true)));
  }
  function inModebar(e) {
    var t = e.target;
    return !!(t && t.closest && t.closest(".modebar"));
  }
  function onTouchStart(e) {
    if (inModebar(e)) { return; }
    e.stopPropagation();
    G = (mode === "chart" && e.touches.length <= 2) ? begin(e.touches) : null;
  }
  function onTouchMove(e) {
    if (inModebar(e)) { return; }
    e.stopPropagation();
    if (mode !== "chart" || !G) { return; }
    if (e.cancelable) { e.preventDefault(); }
    if (e.touches.length !== G.n) { G = e.touches.length <= 2 ? begin(e.touches) : null; return; }
    moveGesture(e.touches);
  }
  function onTouchEnd(e) {
    if (inModebar(e)) { return; }
    e.stopPropagation();
    G = (mode === "chart" && e.touches.length > 0 && e.touches.length <= 2) ? begin(e.touches) : null;
  }
  var opt = {capture: true, passive: false};
  el.addEventListener("touchstart", onTouchStart, opt);
  el.addEventListener("touchmove", onTouchMove, opt);
  el.addEventListener("touchend", onTouchEnd, opt);
  el.addEventListener("touchcancel", onTouchEnd, opt);
  api.reset = function () { schedule(resetUpdate()); };
  api.toggleTouch = function () {          // "chart" = finger pans / pinches the chart, "scroll" = finger scrolls the page
    mode = (mode === "chart") ? "scroll" : "chart";
    el.style.touchAction = (mode === "chart") ? "none" : "auto";
    G = null;
    return mode;
  };
  return api;
}
"""
def render_zoomable_chart(fig, key, height=950):
  fig_json = fig.to_json()
  div_id = f"qfx_chart_{key}"
  btn_css = (
      f"background:{COLOR_PANEL_BG};color:{COLOR_TEXT_MAIN};border:1px solid {COLOR_BORDER};"
      f"border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer;"
  )
  html = f"""
    <div id="{div_id}_wrapper" style="
        resize: both; overflow: auto; width: 100%; height: {height}px;
        min-width: 320px; min-height: 400px; max-width: 100%;
        border: 1px solid {COLOR_BORDER}; border-radius: 6px;
        background-color: {COLOR_BG_DARK}; padding: 4px; box-sizing: border-box;">
      <div id="{div_id}" style="width: 100%; height: 100%; touch-action: none;"></div>
    </div>
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:10px;color:{COLOR_TEXT_MUTED};margin-top:4px;">
      <span>🖱️ Drag = pan • Scroll = zoom • 📱 1 finger = pan • 2 fingers = pinch zoom • all panels move together</span>
      <button id="{div_id}_reset" type="button" style="{btn_css}">↺ Reset view</button>
      <button id="{div_id}_touch" type="button" style="{btn_css}">✋ Touch: pan chart</button>
    </div>
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <script>
      {QFX_SYNC_JS}
      (function() {{
        var figSpec = {fig_json};
        var config = {{
          scrollZoom: true, displaylogo: false, responsive: false, displayModeBar: true,
          modeBarButtonsToRemove: ["select2d", "lasso2d"]
        }};
        var el = document.getElementById("{div_id}");
        Plotly.newPlot(el, figSpec.data, figSpec.layout, config).then(function() {{
          var annotations = el.querySelectorAll('.annotation');
          annotations.forEach(function(ann) {{
            var textEl = ann.querySelector('text');
            if (textEl && (textEl.textContent.includes('BUY') || textEl.textContent.includes('SELL'))) {{
              ann.classList.add('qfx-blinking-signal');
            }}
          }});
          var link = qfxLinkAxes(el, figSpec);
          document.getElementById("{div_id}_reset").onclick = function() {{ link.reset(); }};
          var touchBtn = document.getElementById("{div_id}_touch");
          touchBtn.onclick = function() {{
            touchBtn.textContent = (link.toggleTouch() === "chart") ? "✋ Touch: pan chart" : "📜 Touch: scroll page";
          }};
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
def _md_safe(text):
  # "$" would start LaTeX inside a button label — escape it.
  return text.replace("$", "\\$")
def render_clickable_single_box(title, movers, key_prefix, on_click, compact=False):
  if not movers:
    st.markdown(
        f"<div style='background-color:{COLOR_PANEL_BG};border:1px solid {COLOR_BORDER};"
        f"border-radius:6px;padding:3px 8px;'>"
        f"<div style='font-size:10px;color:{COLOR_TEXT_MUTED};font-weight:600;'>{title}:"
        f" <span style='font-weight:400;'>No data</span></div></div>",
        unsafe_allow_html=True,
    )
    return
  best = movers[0]
  col = "green" if best["chg"] >= 0 else "red"
  arrow = "▲" if best["chg"] >= 0 else "▼"
  label = _md_safe(
      f"{title}: **{best['display']}** ${format_price(best['price'])} :{col}[{arrow} {best['chg']:+.2f}%]"
  )
  st.button(
      label, key=f"qfxtop_{key_prefix}", on_click=on_click,
      args=(best["symbol"], best["display"]), use_container_width=True,
  )
def render_clickable_list_box(title, movers, key_prefix, on_click, value_fmt=None, empty_text="No data"):
  """Header + one real button per row. Clicking a row opens that symbol's chart.
  value_fmt(m) must return Markdown (e.g. ':green[▲ +1.2%]')."""
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
        f"font-size:12px;color:{COLOR_TEXT_MUTED};'>{empty_text}</div>",
        unsafe_allow_html=True,
    )
    return
  for idx, m in enumerate(movers, start=1):
    if value_fmt:
      value_md = value_fmt(m)
    else:
      col = "green" if m["chg"] >= 0 else "red"
      arrow = "▲" if m["chg"] >= 0 else "▼"
      value_md = f":{col}[{arrow} {m['chg']:+.2f}%]"
    st.button(
        _md_safe(f"{idx}. **{m['display']}**  •  {value_md}"),
        key=f"qfxrow_{key_prefix}_{idx}",
        on_click=on_click,
        args=(m["symbol"], m["display"]),
        use_container_width=True,
    )
  st.markdown(f"<div style='height:12px;'></div>", unsafe_allow_html=True)
def render_conviction_box(results_by_cat, key_prefix, on_click):
  st.markdown(
      f"<div style='background-color:{COLOR_PANEL_BG};border:1px solid {COLOR_BORDER};"
      f"border-radius:6px;padding:10px 14px;margin-bottom:8px;'>"
      f"<div style='font-size:12px;color:{COLOR_TEXT_MAIN};font-weight:700;margin-bottom:4px;'>🚨 High-Conviction Shares</div>"
      f"<div style='font-size:10px;color:{COLOR_TEXT_MUTED};line-height:1.5;'>"
      f"Daily: Close &gt; EMA200 • EMA9 &gt; EMA200 &amp; EMA20 • RSI14 &gt; 50 • Close &gt; 5d &amp; 10d-ago high • "
      f"Low ≤ EMA9 &lt; Close • Volume &gt; 20d avg</div></div>",
      unsafe_allow_html=True,
  )
  for cat_name, hits in results_by_cat.items():
    def _value_html(m, cat_name=cat_name):
      col = "green" if m["chg"] >= 0 else "red"
      arrow = "▲" if m["chg"] >= 0 else "▼"
      return f"{conviction_price_str(cat_name, m['price'])} :{col}[{arrow} {m['chg']:+.2f}%]"
    shown = hits[:CONVICTION_MAX_DISPLAY]
    extra = len(hits) - len(shown)
    title = f"{cat_name} • {len(hits)} match{'es' if len(hits) != 1 else ''}"
    if extra > 0:
      title += f" (top {len(shown)} shown)"
    render_clickable_list_box(
        title,
        shown,
        key_prefix=f"{key_prefix}_{cat_name.lower().replace(' ', '')}",
        on_click=on_click,
        value_fmt=_value_html,
        empty_text="No matches",
    )
# =====================================================================
# SIDEBAR CONTROLS
# =====================================================================
st.sidebar.markdown("## 📈 QuantFX Terminal")
st.sidebar.caption("ATR Renko • Heikin Ashi • Pullback Signals")
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
ema_fast = c1.number_input("EMA Fast", min_value=1, max_value=200, value=9)
ema_mid = c2.number_input("EMA Mid", min_value=1, max_value=200, value=27)
ema_slow = c2b.number_input("EMA Slow", min_value=1, max_value=200, value=50)
c3, c4 = st.sidebar.columns(2)
atr_period = c3.number_input("ATR Period", min_value=2, max_value=100, value=21)
atr_multiplier = c4.number_input("ATR Mult.", min_value=0.1, max_value=10.0, value=3.0, step=0.1)
st.sidebar.markdown("---")
SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".qfx_settings.json"
)
def load_settings():
  try:
    if os.path.exists(SETTINGS_PATH):
      with open(SETTINGS_PATH, "r") as f:
        data = json.load(f)
      if isinstance(data, dict):
        return data
  except Exception:
    pass
  return {}
def save_settings(data):
  try:
    with open(SETTINGS_PATH, "w") as f:
      json.dump(data, f)
    return True
  except Exception:
    return False
_saved_settings = load_settings()
with st.sidebar.expander("⚙️ MACD Settings", expanded=False):
  mc1, mc2, mc3 = st.columns(3)
  macd_fast = mc1.number_input("Fast", min_value=1, max_value=100, value=int(_saved_settings.get("macd_fast", 12)), key="macd_fast_in")
  macd_slow = mc2.number_input("Slow", min_value=1, max_value=200, value=int(_saved_settings.get("macd_slow", 26)), key="macd_slow_in")
  macd_signal = mc3.number_input("Signal", min_value=1, max_value=100, value=int(_saved_settings.get("macd_signal", 9)), key="macd_signal_in")
  macd_smooth = st.slider(
      "MACD Smoothing", min_value=1, max_value=15, value=int(_saved_settings.get("macd_smooth", 3)), key="macd_smooth_in",
      help="Extra EMA applied to the MACD line so it (and the histogram) reads less jagged. 1 = classic raw MACD.",
  )
  if st.button("💾 Save MACD settings", use_container_width=True, key="save_macd_settings"):
    ok = save_settings({
        **load_settings(),
        "macd_fast": int(macd_fast), "macd_slow": int(macd_slow),
        "macd_signal": int(macd_signal), "macd_smooth": int(macd_smooth),
    })
    st.success("Saved — these values load automatically next time.") if ok else st.error("Could not write settings file.")
signal_cooldown = st.sidebar.slider(
    "Signal Cooldown (bricks)", min_value=1, max_value=20, value=5,
    help="Minimum bricks between BUY/SELL signals. Higher = fewer, more confident signals.",
)
st.sidebar.caption("EMA Fast × EMA Mid (9 × 27) drives the EMA-cross screener boxes and the Renko / Heikin Ashi Buy/Sell signals.")
st.sidebar.markdown("---")
CHARTINK_EMA_SCREENER_URL = "https://chartink.com/screener/ema9-20-cross-5"
with st.sidebar:
  st.markdown(f"<div style='font-size:11px;color:{COLOR_TEXT_MUTED};font-weight:600;margin-bottom:6px;'>📊 Chartink Screener</div>", unsafe_allow_html=True)
  _sidebar_chartink_hits = fetch_chartink_screener(CHARTINK_EMA_SCREENER_URL)
  render_clickable_list_box(
      "Chartink — EMA 9/20 Cross",
      _sidebar_chartink_hits,
      key_prefix="chartink_ema920_sidebar",
      on_click=go_to_chart,
  )
  st.markdown(
      f"<div style='font-size:11px;margin:2px 0 10px 2px;'>"
      f"<a href='{CHARTINK_EMA_SCREENER_URL}' target='_blank' style='color:{COLOR_TEXT_MUTED};text-decoration:none;'>Open full screener on Chartink ↗</a>"
      f"</div>",
      unsafe_allow_html=True,
  )
st.sidebar.markdown("---")
if "tg_token" not in st.session_state or "tg_chat" not in st.session_state:
  saved_token, saved_chat = load_telegram_config()
  st.session_state["tg_token"] = saved_token
  st.session_state["tg_chat"] = saved_chat
def run_scan_and_send(tg_token, tg_chat, ema_fast, ema_mid, ema_slow):
  """Pushes one Telegram message (auto-split if long) containing:
    * High-Conviction Shares (Nifty 500 / US 100 / Commodities / Forex) —
      the FIRST scan sends the whole list; every later scan sends only the
      stocks that were not in the previous scan's list.
    * 30m 3-EMA cross (either side) for Commodities / Forex.
  Returns (ok, total_alerts, status_text). Shared by the manual button and
  the scheduled auto-scan timer."""
  triggered_messages = []
  state = load_conviction_state()
  prev_last = state.get("last", {})
  prev_ema30 = state.get("ema30")  # None => first scan
  active_ema30 = []
  # --- 30m 3-EMA cross triggers — Commodities / Forex, either side -------
  fx_comm_watchlist = [("Commodities", COMMODITIES), ("Forex", FOREX_PAIRS)]
  for cat_name, symbols in fx_comm_watchlist:
    hits = scan_triple_ema_cross_30m(
        tuple(symbols),
        ema_fast=int(ema_fast),
        ema_mid=int(ema_mid),
        ema_slow=int(ema_slow),
        lookback=1,
    )
    for h in hits:
      if h["bars_ago"] <= 1:
        key = f"{h['display']}|{h['direction']}"
        active_ema30.append(key)
        if prev_ema30 is not None and key in prev_ema30:
          continue  # already alerted on an earlier scan
        emoji = "🟢" if h["direction"] == "BUY" else "🔴"
        triggered_messages.append(
            f"{emoji} *[30m 3-EMA Cross]* *{h['display']}* → *{h['direction']}* "
            f"(EMA {int(ema_fast)}/{int(ema_mid)}/{int(ema_slow)}, {cat_name})"
        )
  # --- High-Conviction Shares: first scan = all, afterwards = new only ----
  new_last = dict(prev_last)
  conviction_lines = []
  conviction_count = 0
  for cat_name, symbols in CONVICTION_UNIVERSE.items():
    hits, n_evaluated = scan_conviction_category(tuple(symbols))
    if n_evaluated == 0:
      continue  # data feed failed — leave this list's memory untouched
    is_first = cat_name not in prev_last
    prev_set = set(prev_last.get(cat_name, []))
    fresh = hits if is_first else [h for h in hits if h["symbol"] not in prev_set]
    new_last[cat_name] = [h["symbol"] for h in hits]
    if not fresh:
      continue
    if conviction_lines:
      conviction_lines.append("")
    conviction_lines.append(f"*{cat_name}* ({'initial scan' if is_first else 'new additions'})")
    for h in fresh:
      conviction_lines.append(
          f"🔥 *{h['display']}* — {conviction_price_str(cat_name, h['price'])} ({h['chg']:+.2f}%)"
      )
    conviction_count += len(fresh)
  message_sections = []
  if conviction_lines:
    message_sections.append("*🚨 High-Conviction Shares*\n" + "\n".join(conviction_lines))
  if triggered_messages:
    message_sections.append("*⚡ 30m 3-EMA Cross — Commodities & Forex*\n" + "\n".join(triggered_messages))
  total_alerts = len(triggered_messages) + conviction_count
  if not message_sections:
    save_conviction_state({"last": new_last, "ema30": active_ema30})
    return True, 0, "No new stocks added to the High-Conviction list since the last scan."
  combined_msg = "📢 *QuantFX Automated Triggers*\n\n" + "\n\n".join(message_sections)
  ok, m = send_telegram_alert_chunked(combined_msg, tg_token, tg_chat)
  if ok:
    # Only remember the list once Telegram accepted it, so a failed send is retried.
    save_conviction_state({"last": new_last, "ema30": active_ema30})
  return ok, total_alerts, m
with st.sidebar.expander("🔔 Telegram Alerts & Automated Triggers", expanded=False):
  tg_token = st.text_input("Bot Token", value=st.session_state.get("tg_token", ""), type="password")
  tg_chat = st.text_input("Chat ID", value=st.session_state.get("tg_chat", ""))
  st.session_state["tg_token"] = tg_token
  st.session_state["tg_chat"] = tg_chat
  bcol1, bcol2 = st.columns(2)
  if bcol1.button("💾 Save credentials", use_container_width=True):
    ok, msg = save_telegram_config(tg_token, tg_chat)
    st.success("Saved.") if ok else st.error(msg)
  if bcol2.button("Test Connection", use_container_width=True):
    ok, msg = send_telegram_alert("🟢 *QuantFX Terminal Test Alert*", tg_token, tg_chat)
    st.success(msg) if ok else st.error(msg)
  st.caption(
      "Auto scan sends: High-Conviction Shares (Nifty 500 / US 100 / Commodities / Forex) — "
      "the full list on the first scan, then only newly added stocks — "
      "plus 30m 3-EMA cross alerts (BUY or SELL) for Commodities/Forex. "
      "Runs automatically every 5 minutes while the app is open."
  )
  if st.button("🚀 Run Auto Scan & Send", use_container_width=True):
    ok, total_alerts, status = run_scan_and_send(
        tg_token, tg_chat, ema_fast, ema_mid, ema_slow
    )
    if not ok:
      st.error(status)
    elif total_alerts == 0:
      st.info(status)
    else:
      st.success(f"Dispatched {total_alerts} alert(s)!")
  if st.button("♻️ Reset alert memory (next scan sends full list)", use_container_width=True):
    save_conviction_state({"last": {}, "ema30": None})
    st.success("Cleared — the next scan will send every current match again.")
AUTO_SCAN_MINUTES = 5
if not AUTOREFRESH_AVAILABLE:
  st.sidebar.warning(
      "Auto-scan every 5 min needs the `streamlit-autorefresh` package. "
      "Run `pip install streamlit-autorefresh` and restart the app."
  )
elif not (tg_token and tg_chat):
  st.sidebar.warning("Auto-scan is waiting for your Telegram Bot Token / Chat ID (open 🔔 Telegram Alerts above and save them).")
else:
  # Always on: scans immediately when the app opens (the first scan sends the
  # full list), then every 5 minutes. Only newly added stocks are sent after that.
  _refresh_count = st_autorefresh(interval=AUTO_SCAN_MINUTES * 60 * 1000, key="qfx_auto_refresh_timer")
  if _refresh_count != st.session_state.get("_qfx_last_autorefresh_count", -1):
    st.session_state["_qfx_last_autorefresh_count"] = _refresh_count
    _ok, _n, _status = run_scan_and_send(tg_token, tg_chat, ema_fast, ema_mid, ema_slow)
    st.session_state["_qfx_last_autorun_at"] = pd.Timestamp.now().strftime("%H:%M:%S")
    st.session_state["_qfx_last_autorun_status"] = "✅ ok" if _ok else f"❌ {_status}"
  st.sidebar.caption(
      f"🟢 Auto-scan every {AUTO_SCAN_MINUTES} min • last run {st.session_state.get('_qfx_last_autorun_at', '—')} "
      f"• {st.session_state.get('_qfx_last_autorun_status', '')}"
  )
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
# =====================================================================
# MAIN LAYOUT
# =====================================================================
_header_top_commodity = fetch_top_n_movers(tuple(COMMODITIES), n=1)
_header_top_forex = fetch_top_n_movers(tuple(FOREX_PAIRS), n=1)
if "active_view" not in st.session_state:
  st.session_state.active_view = VIEWS[0]
live_price, live_chg = get_live_price_and_chg(chart_symbol)
price_str = f"${format_price(live_price)}"
chg_color = COLOR_GREEN if live_chg >= 0 else COLOR_RED
chg_arrow = "▲" if live_chg >= 0 else "▼"
live_str = f"<span style='color:{chg_color};font-weight:700;'>{price_str} {chg_arrow} {live_chg:+.2f}%</span>" if live_price else ""
header_col1, header_col2, top_commodity_col, top_forex_col = st.columns([0.42, 0.28, 0.15, 0.15])
with header_col1:
  st.markdown(
      f"<div style='padding-top:4px;'>"
      f"<span style='color:#FFFFFF;font-size:1.2rem;font-weight:700;'>{chart_display}</span> "
      f"<span style='color:{COLOR_TEXT_MUTED};font-size:10px;'>({chart_symbol}) • {interval}</span> "
      f"<span style='margin-left:8px;font-size:11px;'>{live_str}</span>"
      f"</div>",
      unsafe_allow_html=True,
  )
with header_col2:
  active_view = st.radio("View", VIEWS, horizontal=True, label_visibility="collapsed", key="active_view")
with top_commodity_col:
  render_clickable_single_box("Top Commodity", _header_top_commodity, key_prefix="header_top_commodity", on_click=go_to_chart, compact=True)
with top_forex_col:
  render_clickable_single_box("Top Forex", _header_top_forex, key_prefix="header_top_forex", on_click=go_to_chart, compact=True)
# ---- Charts view --------------------------------------------------------
if active_view == "📊 Charts":
  with st.spinner(f"Fetching {chart_display}..."):
    if interval == "2h":
      raw_df = fetch_2h_ohlc(chart_symbol, period=period)
    else:
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
        macd_smooth=macd_smooth,
        signal_cooldown=signal_cooldown,
    )
    if renko_df.empty:
      st.warning("Not enough data to build ATR Renko bricks for this timeframe.")
    else:
      real_df = raw_df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
      ha_df = compute_heikin_ashi(real_df, ema_fast=ema_fast, ema_slow=ema_slow, ema_mid=ema_mid)  # real Heikin Ashi (actual candles)
      struct_event = latest_structure_event(renko_df, lookback=15)
      with st.spinner("Scanning watchlists..."):
        conviction_results = get_conviction_results()
        ema_cross_nifty, _ = scan_ema_cross_2h(tuple(zip(nifty500_yf, nifty500_raw)), fast=int(ema_fast), slow=int(ema_mid), lookback=1)
        ema_cross_us100, _ = scan_ema_cross_2h(tuple(zip(us100_yf, us100_raw + ["IXIC"])), fast=int(ema_fast), slow=int(ema_mid), lookback=1)
        outlook = compute_7day_outlook(
            chart_symbol,
            chart_display,
            period="1y",
            interval="1d",
            macd_fast=macd_fast,
            macd_slow=macd_slow,
            macd_signal=macd_signal,
        )
      fig = create_chart_figure(
          renko_df, ha_df, brick_size, chart_display, ema_fast, ema_slow, ema_mid,
          live_price=live_price, live_chg=live_chg, symbol_label=chart_display,
          raw_df=real_df,
          macd_params=dict(fast=macd_fast, slow=macd_slow, signal=macd_signal, smooth=macd_smooth),
      )
      chart_col, right_panel_col = st.columns([0.74, 0.26])
      with chart_col:
        search_col, search_btn_col = st.columns([0.85, 0.15])
        search_col.text_input(
            "Quick search",
            key="chart_search_box",
            label_visibility="collapsed",
            placeholder="🔍 Search a symbol to open its chart — e.g. GOLD, MU, EUR/USD...",
            on_change=run_chart_search,
        )
        search_btn_col.button(
            "🔍 Open chart",
            key="chart_search_btn",
            use_container_width=True,
            on_click=run_chart_search,
        )
        render_zoomable_chart(
            fig,
            key=chart_symbol.replace("=", "_").replace("^", "idx"),
            height=950,
        )
        
        if st.button("📨 Send current signal to Telegram"):
          cross_col = renko_df["MACD_Cross_Signal"]
          nonhold = cross_col[cross_col != "HOLD"]
          if not nonhold.empty:
            last_idx = nonhold.index[-1]
            last_cross = nonhold.iloc[-1]
            bricks_ago = (len(renko_df) - 1) - last_idx
            signal_line = f"{last_cross} ({'latest brick' if bricks_ago == 0 else f'{bricks_ago} bricks ago'})"
          else:
            signal_line = "No MACD/Signal cross yet"
          msg = (
              f"*{chart_display}* ({chart_symbol})\n"
              f"Price: ${format_price(float(raw_df['Close'].iloc[-1]))}\n"
              f"MACD/Signal Cross: {signal_line}\n"
              f"Structure: {struct_event['label'] if struct_event else '—'}"
          )
          ok, m = send_telegram_alert(msg, tg_token, tg_chat)
          st.success(m) if ok else st.error(m)
      with right_panel_col:
        def _ema_cross_value_md(cat_name):
          def _fmt(m):
            col = "green" if m["direction"] == "BUY" else "red"
            arrow = "▲" if m["direction"] == "BUY" else "▼"
            recency = "latest" if m["bars_ago"] == 0 else f"{m['bars_ago']} bar ago"
            return f"{conviction_price_str(cat_name, m['price'])} • :{col}[{arrow} {m['direction']}] • {recency}"
          return _fmt
        if outlook:
          dir_color = (
              COLOR_GREEN
              if outlook["direction"] == "Bullish"
              else (COLOR_RED if outlook["direction"] == "Bearish" else COLOR_TEXT_MUTED)
          )
          reasons_html = "".join(
              f"<div style='font-size:11px;color:{COLOR_TEXT_MUTED};margin-top:6px;line-height:1.5;'>• {reason}</div>"
              for reason in outlook.get("reasons", [])
          )
          st.markdown(
              f"<div style='background-color:{COLOR_PANEL_BG};border:1px solid {COLOR_BORDER};"
              f"border-radius:6px;padding:12px 14px;margin-bottom:14px;'>"
              f"<div style='font-size:12px;color:{COLOR_TEXT_MAIN};font-weight:700;margin-bottom:8px;'>🧭 7-Day Detailed Outlook</div>"
              f"<div style='font-size:12px;font-weight:700;color:{dir_color};'>{outlook['direction']}"
              f" <span style='font-size:11px;color:{COLOR_TEXT_MUTED};font-weight:400;'>(Bias Score: {outlook['bias_score']:+.1f})</span></div>"
              f"<div style='font-size:11px;color:{COLOR_TEXT_MUTED};margin-top:5px;'>Projected Range: ${format_price(outlook['range_low'])} – ${format_price(outlook['range_high'])}</div>"
              f"<div style='font-size:11px;color:{COLOR_TEXT_MAIN};font-weight:600;margin-top:8px;'>Bullish / Bearish Drivers:</div>"
              f"{reasons_html}"
              f"</div>",
              unsafe_allow_html=True,
          )
        render_conviction_box(conviction_results, key_prefix="hc", on_click=go_to_chart)
        for _cat, _hits, _kp in (("Nifty 500", ema_cross_nifty, "emax_nifty"), ("US 100", ema_cross_us100, "emax_us100")):
          _shown = _hits[:CONVICTION_MAX_DISPLAY]
          _title = f"⚡ EMA {int(ema_fast)} × {int(ema_mid)} Cross (2H) — {_cat} • {len(_hits)}"
          if len(_hits) > len(_shown):
            _title += f" (newest {len(_shown)} shown)"
          render_clickable_list_box(
              _title, _shown, key_prefix=_kp, on_click=go_to_chart,
              value_fmt=_ema_cross_value_md(_cat), empty_text="No fresh crosses",
          )
# ---- Scanner view ---------------------------------------------------------
elif active_view == "🔎 Scanner":
  st.caption("Runs the oracle score across a watchlist. Click any result to open it in the chart view.")
  cats = st.multiselect("Watchlists to scan", list(WATCHLIST_CATEGORIES.keys()), default=["Commodities", "Forex"])
  if st.button("▶️ Run scanner", type="primary"):
    if not cats:
      st.warning("Pick at least one watchlist.")
    else:
      results = []
      for cat in cats:
        for sym, disp in WATCHLIST_CATEGORIES[cat]:
          res = evaluate_oracle_score(sym, disp, macd_fast=macd_fast, macd_slow=macd_slow, macd_signal=macd_signal)
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
        use_container_width=True,
        hide_index=True,
    )
    oc1, oc2 = st.columns([0.7, 0.3])
    sel_ticker = oc1.selectbox("Open a result in the chart", df_res["Ticker"].tolist(), key="scanner_open_select")
    sel_row = df_res[df_res["Ticker"] == sel_ticker].iloc[0]
    oc2.button(
        "📈 Open chart",
        key="scanner_open_btn",
        use_container_width=True,
        on_click=go_to_chart,
        args=(sel_row["RawSymbol"], sel_row["Ticker"]),
    )
  elif df_res is not None:
    st.info("No results — data source may be rate-limiting.")
