"""
run_scan.py — Standalone scheduled scan for QuantFX Terminal.

This runs OUTSIDE Streamlit entirely, so it works fine on a schedule
(GitHub Actions, a VPS cron, Railway/Render cron, etc). Streamlit
Community Cloud itself cannot run this on a timer — it only wakes up
to serve HTTP requests — so this script must be triggered by something
external to Streamlit. See .github/workflows/hourly_scan.yml.

It reuses the exact same evaluate_oracle_score / send_telegram_alert
logic your app.py uses, just without any st.cache_data / st.session_state
(those are Streamlit-only and unavailable here).
"""

import os
import sys

import indicators as ind

# =====================================================================
# CONFIG — pulled from environment variables (set as GitHub Secrets)
# =====================================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars not set.")
    sys.exit(1)

ind.TELEGRAM_CONFIG["token"] = TELEGRAM_TOKEN
ind.TELEGRAM_CONFIG["chat_id"] = TELEGRAM_CHAT_ID

COMMODITIES = [
    ("GC=F", "GOLD"), ("SI=F", "SILVER"), ("KC=F", "COFFEE"),
    ("CL=F", "CRUDE"), ("NG=F", "GAS"),
]

FOREX = [
    ("EURUSD=X", "EUR/USD"), ("GBPUSD=X", "GBP/USD"),
    ("USDJPY=X", "USD/JPY"), ("AUDUSD=X", "AUD/USD"),
    ("USDCAD=X", "USD/CAD"),
]


def scan_universe(include_wide=True):
    rows = []

    for sym, disp in COMMODITIES:
        r = ind.evaluate_oracle_score(sym, display=disp)
        if r:
            rows.append(r)

    for sym, disp in FOREX:
        r = ind.evaluate_oracle_score(sym, display=disp)
        if r:
            rows.append(r)

    if include_wide:
        nifty_yf = getattr(ind, "nifty200_yf", [])
        nifty_raw = getattr(ind, "nifty200_raw", [])
        for sym, disp in zip(nifty_yf, nifty_raw):
            r = ind.evaluate_oracle_score(sym, display=disp)
            if r:
                rows.append(r)

        us_yf = getattr(ind, "us100_yf", [])
        us_raw = getattr(ind, "us100_raw", [])
        for sym, disp in zip(us_yf, us_raw):
            r = ind.evaluate_oracle_score(sym, display=disp)
            if r:
                rows.append(r)

    return rows


def filter_strict_buys(rows, min_score=50.0, min_tp1_pct=5.0):
    valid = []
    for row in rows:
        try:
            score = float(str(row["Score"]).replace("%", ""))
            tp1_pct = float(str(row["TP1_PCT"]).replace("%", ""))
            signal = str(row["Signal"]).upper()
            if signal == "BUY" and score >= min_score and tp1_pct >= min_tp1_pct:
                valid.append(row)
        except (ValueError, KeyError):
            continue
    return valid


def main():
    include_wide = os.environ.get("INCLUDE_WIDE_UNIVERSE", "true").lower() == "true"

    print(f"Scanning (include_wide={include_wide})...")
    all_rows = scan_universe(include_wide=include_wide)
    print(f"Scanned {len(all_rows)} symbols.")

    valid_buys = filter_strict_buys(all_rows)

    if not valid_buys:
        print("No symbols met strict BUY criteria (Score>=50%, TP1%>=5%). No alert sent.")
        return

    lines = ["*🚨 High-Conviction BUY Alerts* _(Score ≥ 50%, TP1% ≥ 5%)_"]
    for r in valid_buys[:15]:
        lines.append(
            f"• *{r['Ticker']}*: {r['Signal']} | Price: {r['Price']} "
            f"| Score: {r['Score']} | TP1: {r['TP1_PCT']}"
        )

    ok, msg = ind.send_telegram_alert("\n".join(lines))
    if ok:
        print(f"Sent {len(valid_buys)} BUY alerts to Telegram.")
    else:
        print(f"Telegram send failed: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
