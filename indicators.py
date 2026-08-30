"""
indicators.py
Pure calculation layer for the QuantFX terminal, shared by the Streamlit
web app. No PyQt6 / matplotlib dependency here — this file only computes
numbers so it can run anywhere (desktop, server, Streamlit Cloud).
"""
import numpy as np
import pandas as pd
import yfinance as yf
import requests

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
# INDICATORS & MACD CROSSOVER DETECTION (SCREENSHOT 1 STYLE)
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
    """Detects every MACD line and Signal line crossover for Buy/Sell triggers."""
    macd = renko_df["MACD"].values
    signal = renko_df["MACD_Signal"].values
    
    macd_signals = ["HOLD"] * len(renko_df)
    macd_types = [None] * len(renko_df)

    if len(renko_df) < 2:
        return macd_signals, macd_types

    for i in range(1, len(renko_df)):
        # Bullish Crossover: MACD crosses above Signal Line
        if macd[i] >= signal[i] and macd[i - 1] < signal[i - 1]:
            macd_signals[i] = "BUY"
            macd_types[i] = "MACD Cross Up"
        # Bearish Crossover: MACD crosses below Signal Line
        elif macd[i] <= signal[i] and macd[i - 1] > signal[i - 1]:
            macd_signals[i] = "SELL"
            macd_types[i] = "MACD Cross Down"

    return macd_signals, macd_types

def build_atr_renko_df(df,
                       atr_period=14,
                       atr_multiplier=2.0,
                       ema_fast=9,
                       ema_slow=20,
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

    exp1 = r_close.ewm(span=macd_fast, adjust=False).mean()
    exp2 = r_close.ewm(span=macd_slow, adjust=False).mean()
    renko_df["MACD"] = exp1 - exp2
    renko_df["MACD_Signal"] = renko_df["MACD"].ewm(span=macd_signal, adjust=False).mean()
    renko_df["MACD_Hist"] = renko_df["MACD"] - renko_df["MACD_Signal"]

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

    return renko_df, brick_size

# =====================================================================
# DATA SOURCE & UPDATED 7-DAY OUTLOOK
# =====================================================================
def fetch_live_ohlc(symbol="GC=F", period="1mo", interval="1h"):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def evaluate_oracle_score(symbol, display=None):
    try:
        df = fetch_live_ohlc(symbol, period="60d", interval="1h")
        if df.empty:
            return None

        last_close = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2]) if len(df) > 1 else last_close
        chg = ((last_close - prev_close) / prev_close) * 100

        recent = df.tail(24) if len(df) >= 24 else df
        high = float(recent["High"].max())
        low = float(recent["Low"].min())

        daily = df.resample("1D").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last"
        }).dropna()

        atr_source = daily if len(daily) >= 15 else df
        tr1 = atr_source["High"] - atr_source["Low"]
        tr2 = (atr_source["High"] - atr_source["Close"].shift(1)).abs()
        tr3 = (atr_source["Low"] - atr_source["Close"].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        if np.isnan(atr) or atr <= 0:
            atr = last_close * 0.01
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

        tp1_mult = 1.5 * expansion
        tp2_mult = 3.0 * expansion

        sl = low * 0.99 if sig == "BUY" else high * 1.01
        tp1 = last_close + tp1_mult * atr if sig == "BUY" else last_close - tp1_mult * atr
        tp2 = last_close + tp2_mult * atr if sig == "BUY" else last_close - tp2_mult * atr

        tp1_pct = abs((tp1 - last_close) / last_close) * 100
        tp2_pct = abs((tp2 - last_close) / last_close) * 100

        momentum_score = min(momentum_ratio / 2.0, 1.0) * 40
        reward_score = min(tp1_pct / 8.0, 1.0) * 40
        volume_score = min(vol_ratio / 2.0, 1.0) * 20
        score_val = min(max(momentum_score + reward_score + volume_score, 0), 100)
        score_str = f"{score_val:.1f}%"

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
            "Score": score_str,
            "SL": f"{sl:,.{decimals}f}" if is_fx else f"${sl:,.{decimals}f}",
            "TP1": f"{tp1:,.{decimals}f}" if is_fx else f"${tp1:,.{decimals}f}",
            "TP1_PCT": f"{tp1_pct:.2f}%",
            "TP2": f"{tp2:,.{decimals}f}" if is_fx else f"${tp2:,.{decimals}f}"
        }
    except Exception:
        return None

def compute_7day_outlook(symbol, display, period="1y", interval="1d"):
    """Updated 7-day outlook calculation utilizing selected timeframe parameters and context."""
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
        macd_hist = macd - macd_signal

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()

        last_close = float(close.iloc[-1])
        last_ema9, last_ema20 = float(ema9.iloc[-1]), float(ema20.iloc[-1])
        prev_ema9, prev_ema20 = float(ema9.iloc[-2]), float(ema20.iloc[-2])
        last_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
        last_macd_hist = float(macd_hist.iloc[-1])
        prev_macd_hist = float(macd_hist.iloc[-2])
        last_atr = float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else last_close * 0.01
        atr_pct = (last_atr / last_close) * 100

        idx = data.index
        if len(idx) > 5:
            deltas_minutes = np.diff(idx[-30:].values).astype("timedelta64[m]").astype(float)
            deltas_minutes = deltas_minutes[deltas_minutes > 0]
            avg_bar_minutes = float(np.median(deltas_minutes)) if len(deltas_minutes) else 1440.0
        else:
            avg_bar_minutes = 1440.0
        bars_in_7_days = max((7 * 24 * 60) / avg_bar_minutes, 1.0)

        ema9_slope_pct = 0.0
        if len(ema9) > 6 and float(ema9.iloc[-6]) != 0:
            ema9_slope_pct = ((last_ema9 - float(ema9.iloc[-6])) / float(ema9.iloc[-6])) * 100

        reasons = []
        bias_score = 0.0

        if last_ema9 > last_ema20:
            bias_score += 1
            reasons.append(f"EMA9 (${last_ema9:,.2f}) is above EMA20 (${last_ema20:,.2f}), keeping the short-term trend bullish.")
            if prev_ema9 <= prev_ema20:
                bias_score += 1
                reasons.append("EMA9 just crossed above EMA20 - a fresh bullish crossover.")
        else:
            bias_score -= 1
            reasons.append(f"EMA9 (${last_ema9:,.2f}) is below EMA20 (${last_ema20:,.2f}), keeping the short-term trend bearish.")
            if prev_ema9 >= prev_ema20:
                bias_score -= 1
                reasons.append("EMA9 just crossed below EMA20 - a fresh bearish crossover.")

        if ema9_slope_pct > 0.3:
            bias_score += 1
            reasons.append(f"Momentum is accelerating - EMA9 up {ema9_slope_pct:.1f}% over the last 5 {interval} periods.")
        elif ema9_slope_pct < -0.3:
            bias_score -= 1
            reasons.append(f"Momentum is deteriorating - EMA9 down {abs(ema9_slope_pct):.1f}% over the last 5 {interval} periods.")

        if last_rsi >= 70:
            bias_score -= 0.5
            reasons.append(f"RSI is elevated at {last_rsi:.0f}, raising the odds of a short-term pullback or consolidation.")
        elif last_rsi <= 30:
            bias_score += 0.5
            reasons.append(f"RSI is oversold at {last_rsi:.0f}, raising the odds of a short-term bounce.")
        else:
            reasons.append(f"RSI is neutral at {last_rsi:.0f}, not flagging an extreme either way.")

        if last_macd_hist > 0 and last_macd_hist > prev_macd_hist:
            bias_score += 1
            reasons.append("MACD histogram is positive and expanding - bullish momentum is building.")
        elif last_macd_hist > 0 and last_macd_hist <= prev_macd_hist:
            reasons.append("MACD histogram is positive but shrinking - bullish momentum may be fading.")
        elif last_macd_hist < 0 and last_macd_hist < prev_macd_hist:
            bias_score -= 1
            reasons.append("MACD histogram is negative and expanding - bearish momentum is building.")
        else:
            reasons.append("MACD histogram is negative but shrinking - bearish momentum may be fading.")

        # --- ATR Renko + Heikin Ashi confirmation (previously computed for the
        # charts only, now actually folded into the bias score) ---
        renko_df, _ = build_atr_renko_df(
            data, atr_period=14, atr_multiplier=2.0,
            ema_fast=9, ema_slow=20,
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
                reasons.append(
                    f"ATR Renko trend is bullish - fast EMA (${renko_fast:,.2f}) is above slow EMA (${renko_slow:,.2f}) on the brick chart."
                )
            else:
                bias_score -= 0.5
                reasons.append(
                    f"ATR Renko trend is bearish - fast EMA (${renko_fast:,.2f}) is below slow EMA (${renko_slow:,.2f}) on the brick chart."
                )

            if last_renko_type == "up":
                bias_score += 0.5
                reasons.append(f"Most recent Renko brick printed up, closing at ${last_renko_close:,.2f}.")
            else:
                bias_score -= 0.5
                reasons.append(f"Most recent Renko brick printed down, closing at ${last_renko_close:,.2f}.")

            ha_df = compute_heikin_ashi(renko_df)
            ha_lookback = ha_df.tail(3)
            ha_bull_count = int((ha_lookback["Close"] >= ha_lookback["Open"]).sum())
            ha_bear_count = len(ha_lookback) - ha_bull_count
            if ha_bull_count > ha_bear_count:
                bias_score += 0.5
                reasons.append(f"Heikin Ashi is mostly bullish over the last {len(ha_lookback)} bricks ({ha_bull_count}/{len(ha_lookback)} green).")
            elif ha_bear_count > ha_bull_count:
                bias_score -= 0.5
                reasons.append(f"Heikin Ashi is mostly bearish over the last {len(ha_lookback)} bricks ({ha_bear_count}/{len(ha_lookback)} red).")
            else:
                reasons.append("Heikin Ashi is split evenly over the last few bricks - no clear confirmation.")
        else:
            reasons.append("Not enough ATR Renko bricks yet to confirm with Renko / Heikin Ashi.")

        # Wider bias range now that Renko/HA contribute up to +/-1.5, so the
        # bullish/bearish thresholds move up from 1.5 to 2.0 to keep the same
        # relative strictness.
        if bias_score >= 2.0:
            direction = "Bullish"
        elif bias_score <= -2.0:
            direction = "Bearish"
        else:
            direction = "Neutral / Range-bound"

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
            "last_ema9": last_ema9,
            "last_ema20": last_ema20,
            "last_rsi": last_rsi,
            "last_macd": float(macd.iloc[-1]),
            "last_macd_signal": float(macd_signal.iloc[-1]),
        }
    except Exception:
        return None

# =====================================================================
# NIFTY200 + US100 LISTS (RAW)
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