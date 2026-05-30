#!/usr/bin/env python3
"""
Earnings reminder utility.
v3.5

Checks holdings for upcoming earnings and pushes Telegram alerts.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
import yfinance as yf

from core.notifier import send_telegram_message
from services.datahub.cache import DataCache

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# --- yfinance cache 重定向到项目可写路径 ---
_YF_CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "cache", "yfinance")
os.makedirs(_YF_CACHE_DIR, exist_ok=True)
yf.set_tz_cache_location(_YF_CACHE_DIR)

# --- 业务级缓存: earnings date 每天查一次即可 ---
_earnings_cache = DataCache(
    cache_dir=os.path.join(PROJECT_ROOT, "data", "cache"),
    default_ttl=24 * 3600,
)

DEFAULT_HOLDINGS_PATH = os.path.join(PROJECT_ROOT, "Config", "holdings.json")
LOOKAHEAD_DAYS = 7


def get_tickers_from_holdings(holdings_path: str | None = None) -> list[str]:
    """Read the ticker list from holdings.json."""
    if holdings_path is None:
        holdings_path = DEFAULT_HOLDINGS_PATH
    if not os.path.exists(holdings_path):
        print(f"holdings.json not found: {holdings_path}")
        return []
    try:
        with open(holdings_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return list(data.get("tickers", {}).keys())
    except Exception as exc:
        print(f"Failed to read holdings.json: {exc}")
        return []


def _get_earnings_date(ticker_symbol: str) -> datetime | None:
    """Try to fetch the next earnings date from yfinance.

    Handles both the legacy DataFrame format and the newer dict format
    returned by recent yfinance versions.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        calendar = ticker.calendar
        if calendar is None:
            return None

        dates: list = []

        # New yfinance versions return a plain dict
        if isinstance(calendar, dict):
            raw = calendar.get("Earnings Date")
            if raw is None:
                return None
            dates = raw if isinstance(raw, list) else [raw]

        # Legacy: DataFrame with "Earnings Date" column
        elif hasattr(calendar, "columns") and "Earnings Date" in calendar.columns:
            dates = calendar["Earnings Date"].dropna().tolist()

        # Legacy: DataFrame with "Earnings Date" as index row
        elif hasattr(calendar, "index") and "Earnings Date" in calendar.index:
            value = calendar.loc["Earnings Date"]
            dates = list(value) if hasattr(value, "__iter__") and not isinstance(value, str) else [value]

        for item in dates:
            if isinstance(item, datetime):
                return item
            # datetime.date → datetime
            if hasattr(item, "year") and not isinstance(item, datetime):
                return datetime(item.year, item.month, item.day)
            try:
                return item.to_pydatetime()
            except Exception:
                continue
        return None
    except Exception as exc:
        print(f"Failed to fetch earnings date for {ticker_symbol}: {exc}")
        return None


def get_earnings_date_cached(ticker_symbol: str) -> datetime | None:
    """Cached wrapper — fetches from yfinance at most once per 24h per ticker."""
    cached = _earnings_cache.get("earnings_date", ticker_symbol)
    if cached is not None:
        return datetime.fromisoformat(cached) if cached else None
    result = _get_earnings_date(ticker_symbol)
    _earnings_cache.set(
        "earnings_date",
        ticker_symbol,
        result.isoformat() if result else "",
    )
    return result


def check_and_notify_earnings(
    holdings_path: str | None = None,
    lookahead_days: int = LOOKAHEAD_DAYS,
):
    """Check for upcoming earnings and send a Telegram message if needed."""
    tickers = get_tickers_from_holdings(holdings_path)
    if not tickers:
        print("No holdings found, skipping earnings reminder.")
        return

    deadline = datetime.now() + timedelta(days=lookahead_days)
    upcoming = []

    print(f"Checking earnings dates within the next {lookahead_days} days...")
    for symbol in tickers:
        print(f"  {symbol}...")
        earnings_dt = _get_earnings_date(symbol)
        if earnings_dt and earnings_dt <= deadline:
            days_left = max(0, (earnings_dt - datetime.now()).days)
            upcoming.append(
                {
                    "ticker": symbol,
                    "earnings_date": earnings_dt.strftime("%Y-%m-%d"),
                    "days_left": days_left,
                }
            )

    if not upcoming:
        print("No earnings within the lookahead window.")
        return

    lines = [
        "*Earnings Reminder / 财报*",
        f"As of {datetime.now().strftime('%Y-%m-%d')}, upcoming earnings in the next {lookahead_days} days:",
        "",
    ]
    for item in sorted(upcoming, key=lambda row: row["days_left"]):
        urgency = "Soon" if item["days_left"] <= 2 else "Upcoming"
        lines.append(
            f"{urgency} | {item['ticker']} | {item['earnings_date']} | {item['days_left']} days"
        )

    lines.append("")
    lines.append("Suggested follow-up: run /update or /deep before the event.")

    message = "\n".join(lines)
    print(f"Sending earnings reminder for {len(upcoming)} tickers...")
    send_telegram_message(message)
    print("Earnings reminder sent.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send earnings reminders for holdings.")
    parser.add_argument("--holdings", type=str, default=None, help="Path to holdings.json")
    parser.add_argument("--days", type=int, default=LOOKAHEAD_DAYS, help="Lookahead window in days")
    args = parser.parse_args()

    check_and_notify_earnings(
        holdings_path=args.holdings,
        lookahead_days=args.days,
    )
