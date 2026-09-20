# =====================================================================
# HOW TO APPLY (replaces the earlier qfx_core_patch.py - this one already contains it)
# In qfx_core.py, delete everything from the line
#     # ---- alert look & rules ...     (if you already pasted the earlier patch)
# or from the line
#     # ---- the alert run (shared by the dashboard button, ...     (if you have not)
# down to the end of the file, and paste THIS whole file in its place.
# app.py and scan_job.py need no changes.
# =====================================================================

# ---- alert look & rules -----------------------------------------------------
# Flag shown in front of every alert line (replaces the old fire emoji).
CATEGORY_FLAG = {
    "Nifty 500": "🇮🇳",
    "US 100": "🇺🇸",
    "Commodities": "🇦🇺",
    "Forex": "🇦🇺",
}

# Which sides may be alerted per category: stocks = BUY only, Commodities / Forex = BUY and SELL.
ALERT_SIDES = {
    "Nifty 500": ("BUY",),
    "US 100": ("BUY",),
    "Commodities": ("BUY", "SELL"),
    "Forex": ("BUY", "SELL"),
}

# "First alert of the day" rolls over at midnight in this timezone (override with env var QFX_TZ).
# On Windows, ZoneInfo needs:  pip install tzdata
ALERT_DAY_TZ = os.environ.get("QFX_TZ", "Australia/Melbourne")


def _today_str():
  from datetime import datetime
  try:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(ALERT_DAY_TZ)).strftime("%Y-%m-%d")
  except Exception:
    return datetime.now().strftime("%Y-%m-%d")


def scan_ema_cross_1h(symbols_tuple, fast=9, slow=27, lookback=1):
  """1H EMA fast/slow cross screener over a whole watchlist (batched 60m download, no resampling).
  Returns (hits, n_evaluated); hits sorted newest cross first. n_evaluated == 0 means the feed failed."""
  symbols = list(symbols_tuple)
  hits, n_evaluated = [], 0
  for start in range(0, len(symbols), 100):
    chunk = symbols[start:start + 100]
    data = yf_download([t for t, _ in chunk], period="60d", interval="60m",
                       group_by="ticker", threads=True)
    if data is None or data.empty:
      continue
    for sym, disp in chunk:
      try:
        sub = _frame_for_symbol(data, sym)
        if sub is None or "Close" not in sub.columns:
          continue
        close = sub["Close"].dropna()
        if len(close) < int(slow) + 3:
          continue
        n_evaluated += 1
        cross = detect_ema_cross(close, fast=fast, slow=slow, lookback=lookback)
        if not cross:
          continue
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        hits.append({
            "symbol": sym, "display": disp, "price": last,
            "chg": ((last - prev) / prev * 100) if prev else 0.0,
            "direction": cross["direction"], "bars_ago": cross["bars_ago"],
        })
      except Exception:
        continue
  hits.sort(key=lambda r: (r["bars_ago"], r["direction"] != "BUY", -abs(r["chg"])))
  return hits, n_evaluated


# ---- the alert run (shared by the dashboard button, the in-app timer and scan_job.py) ----
def run_scan_and_send(tg_token, tg_chat, ema_fast, ema_mid, ema_slow, *,
                      conviction_scan=None, cross30_scan=None, cross1h_scan=None, state_path=None,
                      dry_run=False, seed_only=False, full_list=False, log=None):
  """Builds ONE Telegram message (auto-split if long):
    * FIRST alert of each day (Melbourne time): the complete High-Conviction list, every active
      1H EMA fast x mid cross (9 x 27 by default) and every active 30m 3-EMA cross.
    * Every later alert that day: only what is NEW since the previous alert.
        - Nifty 500 / US 100: BUY only.
        - Commodities / Forex: BUY and SELL.
    * Flags in front of each line: India / US / Australia.
  full_list=True sends the COMPLETE current list regardless of what was sent before, and leaves
  the alert memory untouched.
  Returns (ok, total_alerts, status_text)."""
  conviction_scan = conviction_scan or scan_conviction_category
  cross30_scan = cross30_scan or scan_triple_ema_cross_30m
  cross1h_scan = cross1h_scan or scan_ema_cross_1h
  say = log or (lambda *_a, **_k: None)

  state = load_conviction_state(state_path)
  today = _today_str()
  new_day = state.get("day") != today          # no "day" saved (old state file / reset button) also counts
  send_all = full_list or new_day              # True => this is the first alert of the day
  prev_last = {} if new_day else state.get("last", {})
  prev_ema30 = None if new_day else state.get("ema30")    # None => nothing sent yet today
  prev_ema1h = None if new_day else state.get("ema1h")
  active_ema30 = []
  active_ema1h = []
  triggered_messages = []
  ema1h_lines = []
  ema1h_count = 0
  any_data = False

  # --- 30m 3-EMA cross triggers - Commodities / Forex ---------------------
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
    allowed = ALERT_SIDES.get(cat_name, ("BUY", "SELL"))
    for h in hits:
      if h["direction"] not in allowed:
        continue
      if h["bars_ago"] <= 1:
        key = f"{h['display']}|{h['direction']}"
        active_ema30.append(key)
        if not send_all and prev_ema30 is not None and key in prev_ema30:
          continue  # already alerted on an earlier scan
        emoji = "🟢" if h["direction"] == "BUY" else "🔴"
        triggered_messages.append(
            f"{emoji} *[30m 3-EMA Cross]* *{h['display']}* → *{h['direction']}* "
            f"(EMA {int(ema_fast)}/{int(ema_mid)}/{int(ema_slow)}, {cat_name})"
        )

  # --- 1H EMA fast x mid cross (9 x 27) - all four lists ----------------------
  for cat_name, symbols in CONVICTION_UNIVERSE.items():
    hits, n_eval = cross1h_scan(tuple(symbols), fast=int(ema_fast), slow=int(ema_mid), lookback=1)
    say(f"[1H EMA {int(ema_fast)}x{int(ema_mid)}] {cat_name}: {len(hits)} cross(es) in {n_eval} symbols evaluated")
    if n_eval == 0:
      active_ema1h += [k for k in (prev_ema1h or []) if k.startswith(f"{cat_name}|")]
      continue
    any_data = True
    flag = CATEGORY_FLAG.get(cat_name, "")
    allowed = ALERT_SIDES.get(cat_name, ("BUY", "SELL"))
    fresh = []
    for h in hits:
      if h["direction"] not in allowed or h["bars_ago"] > 1:
        continue
      key = f"{cat_name}|{h['display']}|{h['direction']}"
      active_ema1h.append(key)
      if not send_all and prev_ema1h is not None and key in prev_ema1h:
        continue  # already alerted on an earlier scan
      fresh.append(h)
    if not fresh:
      continue
    if ema1h_lines:
      ema1h_lines.append("")
    ema1h_lines.append(f"*{cat_name}* — {len(fresh)}")
    for h in fresh:
      emoji = "🟢" if h["direction"] == "BUY" else "🔴"
      ema1h_lines.append(
          f"{flag} {emoji} *{h['display']}* → *{h['direction']}* — {conviction_price_str(cat_name, h['price'])}"
      )
    ema1h_count += len(fresh)

  # --- High-Conviction Shares: first alert of the day = all, afterwards = new only ----
  new_last = {} if new_day else dict(prev_last)
  conviction_lines = []
  conviction_count = 0
  for cat_name, symbols in CONVICTION_UNIVERSE.items():
    hits, n_evaluated = conviction_scan(tuple(symbols))
    say(f"[High-Conviction] {cat_name}: {len(hits)} match(es) of {n_evaluated} evaluated")
    if n_evaluated == 0:
      continue  # data feed failed - leave this list's memory untouched (it is sent in full next scan)
    any_data = True
    flag = CATEGORY_FLAG.get(cat_name, "🔥")
    is_first = send_all or cat_name not in prev_last
    prev_set = set(prev_last.get(cat_name, []))
    fresh = hits if is_first else [h for h in hits if h["symbol"] not in prev_set]
    new_last[cat_name] = [h["symbol"] for h in hits]
    if send_all and not fresh:
      if conviction_lines:
        conviction_lines.append("")
      conviction_lines.append(f"*{cat_name}* (full list) — no matches")
      continue
    if not fresh:
      continue
    if conviction_lines:
      conviction_lines.append("")
    label = "full list" if send_all else ("initial scan" if is_first else "new additions")
    conviction_lines.append(f"*{cat_name}* ({label}) — {len(fresh)}")
    for h in fresh:
      conviction_lines.append(
          f"{flag} *{h['display']}* — {conviction_price_str(cat_name, h['price'])} ({h['chg']:+.2f}%)"
      )
    conviction_count += len(fresh)

  if not any_data:
    return False, 0, ("No market data came back from Yahoo Finance (rate-limited or offline?) - "
                      "nothing was evaluated, alert memory left untouched.")

  new_state = {"last": new_last, "ema30": active_ema30, "ema1h": active_ema1h, "day": today}
  if seed_only and not full_list:
    save_conviction_state(new_state, state_path)
    return True, 0, "Seeded alert memory with the current matches (nothing sent)."

  message_sections = []
  if conviction_lines:
    message_sections.append("*🚨 High-Conviction Shares*\n" + "\n".join(conviction_lines))
  if ema1h_lines:
    message_sections.append(f"*⏱ 1H EMA {int(ema_fast)} × {int(ema_mid)} Cross*\n" + "\n".join(ema1h_lines))
  if triggered_messages:
    message_sections.append("*⚡ 30m 3-EMA Cross — Commodities & Forex*\n" + "\n".join(triggered_messages))
  total_alerts = len(triggered_messages) + conviction_count + ema1h_count

  if not message_sections:
    if not dry_run and not full_list:
      save_conviction_state(new_state, state_path)
    return True, 0, "No new alerts since the last scan."

  combined_msg = "📢 *QuantFX Automated Triggers*\n\n" + "\n\n".join(message_sections)
  if dry_run:
    say("---- DRY RUN: this is what would be sent ----\n" + combined_msg)
    return True, total_alerts, "Dry run - nothing sent, alert memory not saved."

  ok, m = send_telegram_alert_chunked(combined_msg, tg_token, tg_chat)
  if ok and not full_list:
    # Only remember the list once Telegram accepted it, so a failed send is retried.
    save_conviction_state(new_state, state_path)
  return ok, total_alerts, m
