"""
qfx_core.py - Streamlit-free logic shared by app.py (dashboard) and scan_job.py (headless alert job).

Everything that decides "is there an alert?" lives here, so the dashboard and the
background job can never disagree:
  * watchlists (Nifty 500 / US 100 / Commodities / Forex)
  * High-Conviction daily EMA-9 pullback clause
  * 30m 3-EMA cross (Commodities / Forex) and 2H EMA-cross screener
  * Telegram sending (auto-split, Markdown fallback) and the "only send what is new" state file
"""
import json
import os
import time

import numpy as np
import pandas as pd
import requests
import yfinance as yf

_HERE = os.path.dirname(os.path.abspath(__file__))
TG_CONFIG_PATH = os.path.join(_HERE, ".qfx_telegram_config.json")
CONVICTION_STATE_PATH = os.environ.get("QFX_STATE_PATH") or os.path.join(
    _HERE, ".qfx_conviction_state.json"
)

# =====================================================================
# WATCHLISTS
# =====================================================================

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

CONVICTION_UNIVERSE = {
    "Nifty 500": list(zip(nifty500_yf, nifty500_raw)),
    "US 100": list(zip(us100_yf, us100_raw + ["IXIC"])),
    "Commodities": list(COMMODITIES),
    "Forex": list(FOREX_PAIRS),
}

CONVICTION_CURRENCY = {"Nifty 500": "₹", "US 100": "$", "Commodities": "$", "Forex": ""}

# =====================================================================
# INDICATORS
# =====================================================================

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

def conviction_price_str(cat_name, price):
  cur = CONVICTION_CURRENCY.get(cat_name, "")
  return f"{cur}{format_price(price)}" if cat_name == "Forex" else f"{cur}{price:,.2f}"

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

# =====================================================================
# TELEGRAM
# =====================================================================

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

  def _post(parse_mode):
    payload = {"chat_id": chat_id, "text": message}
    if parse_mode:
      payload["parse_mode"] = parse_mode
    resp = requests.post(url, json=payload, timeout=15)
    try:
      return resp.json()
    except ValueError:
      return {"ok": False, "description": f"HTTP {resp.status_code}"}

  try:
    data = _post("Markdown")
    if not data.get("ok") and "parse entities" in str(data.get("description", "")).lower():
      # a stray * or _ in a ticker must not swallow the alert - resend as plain text
      data = _post(None)
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
    if i < total:
      time.sleep(0.5)
  return all_ok, ("Success" if all_ok else last_err)

# =====================================================================
# DATA + SCANNERS + ALERT RUN
# =====================================================================

def yf_download(tickers, retries=3, pause=2.0, **kw):
  """yf.download with retry/backoff. Returns an empty DataFrame instead of raising,
  so one throttled request never crashes a whole scan."""
  kw.setdefault("progress", False)
  kw.setdefault("timeout", 30)
  for attempt in range(retries):
    try:
      data = yf.download(tickers, **kw)
      if data is not None and not data.empty:
        return data
    except Exception:
      pass
    if attempt < retries - 1:
      time.sleep(pause * (attempt + 1))
  return pd.DataFrame()


def fetch_ohlc(symbol, period="6mo", interval="1d"):
  """Single-symbol OHLC with flat columns (Open/High/Low/Close/Volume)."""
  df = yf_download(symbol, retries=2, period=period, interval=interval)
  if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)
  return df


def resample_2h(df):
  if df is None or df.empty:
    return df
  agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
  if "Volume" in df.columns:
    agg["Volume"] = "sum"
  return df.resample("2h").agg(agg).dropna(subset=["Close"])


# ---- alert memory ("only send what is new") --------------------------------
def load_conviction_state(path=None):
  path = path or CONVICTION_STATE_PATH
  try:
    if os.path.exists(path):
      with open(path, "r") as f:
        data = json.load(f)
      if isinstance(data, dict) and isinstance(data.get("last"), dict):
        return data
  except Exception:
    pass
  return {"last": {}}


def save_conviction_state(state, path=None):
  path = path or CONVICTION_STATE_PATH
  try:
    with open(path, "w") as f:
      json.dump(state, f)
    return True
  except Exception:
    return False


# ---- scanners ---------------------------------------------------------------
def scan_conviction_category(symbols_tuple):
  """Runs the daily EMA-9 pullback clause over one watchlist. Returns (hits, n_evaluated).
  n_evaluated == 0 means the data feed failed, so callers must not treat an empty
  hit list as 'nothing matched'."""
  symbols = list(symbols_tuple)
  hits = []
  n_evaluated = 0
  for start in range(0, len(symbols), 100):
    chunk = symbols[start:start + 100]
    tickers = [s for s, _ in chunk]
    data = yf_download(tickers, period="2y", interval="1d", group_by="ticker", threads=True)
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


def scan_ema_cross_2h(symbols_tuple, fast=9, slow=27, lookback=1):
  """2H EMA fast/slow cross screener over a whole watchlist (batched download).
  Returns (hits, n_evaluated); hits sorted newest cross first."""
  symbols = list(symbols_tuple)
  hits, n_evaluated = [], 0
  agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
  for start in range(0, len(symbols), 100):
    chunk = symbols[start:start + 100]
    data = yf_download([t for t, _ in chunk], period="60d", interval="60m",
                       group_by="ticker", threads=True)
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


def scan_triple_ema_cross_30m(symbols_tuple, ema_fast=9, ema_mid=21, ema_slow=50, lookback=1):
  """30m 3-EMA alignment cross over a small watchlist (one batched download).
  Returns (hits, n_evaluated); n_evaluated == 0 means the feed failed."""
  symbols = list(symbols_tuple)
  hits, n_evaluated = [], 0
  data = yf_download([t for t, _ in symbols], period="10d", interval="30m",
                     group_by="ticker", threads=True)
  if data is None or data.empty:
    return hits, 0
  for sym, disp in symbols:
    try:
      sub = _frame_for_symbol(data, sym)
      if sub is None or "Close" not in sub.columns:
        continue
      close = sub["Close"].dropna()
      if len(close) < ema_slow + 5:
        continue
      n_evaluated += 1
      cross = detect_triple_ema_cross_signal(
          close, fast=ema_fast, mid=ema_mid, slow=ema_slow, lookback=lookback
      )
      if cross:
        hits.append({"symbol": sym, "display": disp, **cross})
    except Exception:
      continue
  return hits, n_evaluated


# ---- the alert run (shared by the dashboard button, the in-app timer and scan_job.py) ----
def run_scan_and_send(tg_token, tg_chat, ema_fast, ema_mid, ema_slow, *,
                      conviction_scan=None, cross30_scan=None, state_path=None,
                      dry_run=False, seed_only=False, log=None):
  """Builds ONE Telegram message (auto-split if long):
    * High-Conviction Shares (Nifty 500 / US 100 / Commodities / Forex) - the FIRST scan
      sends the whole list; every later scan sends only stocks not in the previous list.
    * 30m 3-EMA cross (either side) for Commodities / Forex.
  Returns (ok, total_alerts, status_text)."""
  conviction_scan = conviction_scan or scan_conviction_category
  cross30_scan = cross30_scan or scan_triple_ema_cross_30m
  say = log or (lambda *_a, **_k: None)

  state = load_conviction_state(state_path)
  prev_last = state.get("last", {})
  prev_ema30 = state.get("ema30")  # None => first scan
  active_ema30 = []
  triggered_messages = []
  any_data = False

  # --- 30m 3-EMA cross triggers - Commodities / Forex, either side -------
  for cat_name, symbols in (("Commodities", COMMODITIES), ("Forex", FOREX_PAIRS)):
    hits, n_eval = cross30_scan(
        tuple(symbols), ema_fast=int(ema_fast), ema_mid=int(ema_mid),
        ema_slow=int(ema_slow), lookback=1,
    )
    say(f"[30m 3-EMA] {cat_name}: {len(hits)} cross(es) in {n_eval} symbols evaluated")
    if n_eval == 0:
      # data feed failed for this list - remember what we already knew so nothing is re-sent later
      names = {d for _, d in symbols}
      active_ema30 += [k for k in (prev_ema30 or []) if k.split("|")[0] in names]
      continue
    any_data = True
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
    hits, n_evaluated = conviction_scan(tuple(symbols))
    say(f"[High-Conviction] {cat_name}: {len(hits)} match(es) of {n_evaluated} evaluated")
    if n_evaluated == 0:
      continue  # data feed failed - leave this list's memory untouched
    any_data = True
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

  if not any_data:
    return False, 0, ("No market data came back from Yahoo Finance (rate-limited or offline?) - "
                      "nothing was evaluated, alert memory left untouched.")

  new_state = {"last": new_last, "ema30": active_ema30}
  if seed_only:
    save_conviction_state(new_state, state_path)
    return True, 0, "Seeded alert memory with the current matches (nothing sent)."

  message_sections = []
  if conviction_lines:
    message_sections.append("*🚨 High-Conviction Shares*\n" + "\n".join(conviction_lines))
  if triggered_messages:
    message_sections.append("*⚡ 30m 3-EMA Cross — Commodities & Forex*\n" + "\n".join(triggered_messages))
  total_alerts = len(triggered_messages) + conviction_count

  if not message_sections:
    if not dry_run:
      save_conviction_state(new_state, state_path)
    return True, 0, "No new stocks added to the High-Conviction list since the last scan."

  combined_msg = "📢 *QuantFX Automated Triggers*\n\n" + "\n\n".join(message_sections)
  if dry_run:
    say("---- DRY RUN: this is what would be sent ----\n" + combined_msg)
    return True, total_alerts, "Dry run - nothing sent, alert memory not saved."

  ok, m = send_telegram_alert_chunked(combined_msg, tg_token, tg_chat)
  if ok:
    # Only remember the list once Telegram accepted it, so a failed send is retried.
    save_conviction_state(new_state, state_path)
  return ok, total_alerts, m
