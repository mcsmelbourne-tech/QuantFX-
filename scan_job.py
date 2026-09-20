#!/usr/bin/env python3
"""
scan_job.py - headless QuantFX alert job (no Streamlit, no browser, no open tab).

Runs ONE scan and sends the same Telegram alerts as the dashboard's "Run Auto Scan & Send":
  * High-Conviction Shares (Nifty 500 / US 100 / Commodities / Forex) - the first run sends the whole
    list, every later run sends only stocks that were not in the previous list
  * 30m 3-EMA cross (BUY or SELL) for Commodities / Forex

Run it from any scheduler (GitHub Actions, cron on a small server, Task Scheduler ...):
    python scan_job.py                 # scan + send
    python scan_job.py --dry-run       # scan, print what WOULD be sent, send nothing
    python scan_job.py --test          # just send a "connected" message to check the credentials
    python scan_job.py --full-list     # send the COMPLETE current stock list now
    python scan_job.py --seed-only     # remember today's matches WITHOUT sending (skip the big first message)
    python scan_job.py --reset-state   # forget alert memory (next run sends the full list again)

Credentials come from environment variables (never put them in the code):
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Optional: EMA_FAST / EMA_MID / EMA_SLOW (default 9 / 27 / 50), QFX_STATE_PATH (where alert memory is kept).

Exit codes: 0 = ran fine (even if nothing new), 1 = no data / Telegram send failed, 2 = credentials missing.
"""
import argparse
import os
import sys
import time

import qfx_core


def _env_int(name, default):
  try:
    return int(os.environ.get(name, default))
  except ValueError:
    return default


def main():
  ap = argparse.ArgumentParser(description="QuantFX headless scan + Telegram alert job")
  ap.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
  ap.add_argument("--test", action="store_true", help="send a test message and exit")
  ap.add_argument("--full-list", action="store_true", help="send the COMPLETE current stock list now (ignores what was sent before)")
  ap.add_argument("--seed-only", action="store_true", help="record current matches without sending")
  ap.add_argument("--reset-state", action="store_true", help="forget alert memory first")
  ap.add_argument("--ema-fast", type=int, default=_env_int("EMA_FAST", 9))
  ap.add_argument("--ema-mid", type=int, default=_env_int("EMA_MID", 27))
  ap.add_argument("--ema-slow", type=int, default=_env_int("EMA_SLOW", 50))
  args = ap.parse_args()

  token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
  chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
  if not (token and chat):                      # fall back to the dashboard's saved credentials (local runs)
    saved_token, saved_chat = qfx_core.load_telegram_config()
    token, chat = token or saved_token, chat or saved_chat
  needs_telegram = not (args.dry_run or args.seed_only)
  if needs_telegram and not (token and chat):
    print("ERROR: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (GitHub: Settings > Secrets and variables > Actions).")
    return 2

  if args.test:
    ok, msg = qfx_core.send_telegram_alert("🟢 *QuantFX cloud job connected* — alerts will arrive here.", token, chat)
    print("Telegram test:", "sent" if ok else f"FAILED - {msg}")
    return 0 if ok else 1

  if args.reset_state:
    qfx_core.save_conviction_state({"last": {}, "ema30": None})
    print("Alert memory cleared.")

  t0 = time.time()
  stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
  print(f"QuantFX scan started {stamp}  (EMA {args.ema_fast}/{args.ema_mid}/{args.ema_slow})")
  ok, total_alerts, status = qfx_core.run_scan_and_send(
      token, chat, args.ema_fast, args.ema_mid, args.ema_slow,
      dry_run=args.dry_run, seed_only=args.seed_only, full_list=args.full_list, log=print,
  )
  print(f"Result: ok={ok} alerts={total_alerts} | {status} | {time.time() - t0:.0f}s")
  return 0 if ok else 1


if __name__ == "__main__":
  sys.exit(main())
