#!/usr/bin/env python3
"""
Weekly position report utility.
v3.5

Builds a simple weekly holdings performance summary and sends it to Telegram.
"""

import argparse
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
import yfinance as yf
from google import genai

from core.notifier import send_telegram_message

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

DEFAULT_HOLDINGS_PATH = os.path.join(PROJECT_ROOT, "Config", "holdings.json")
GEMINI_MODEL = "gemini-2.0-flash"

_gemini_key = os.getenv("GEMINI_API_KEY")
_genai_client = genai.Client(api_key=_gemini_key) if _gemini_key else None


def _load_tickers(holdings_path: str) -> dict:
    """Read tickers from holdings.json and return {ticker: info}."""
    if not os.path.exists(holdings_path):
        print(f"holdings.json not found: {holdings_path}")
        return {}
    try:
        with open(holdings_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("tickers", {})
    except Exception as exc:
        print(f"Failed to read holdings.json: {exc}")
        return {}


def calculate_weekly_pnl(holdings_path: str | None = None) -> dict:
    """Calculate 5-day percentage change for each holding."""
    if holdings_path is None:
        holdings_path = DEFAULT_HOLDINGS_PATH

    tickers = _load_tickers(holdings_path)
    result = {}

    for symbol in tickers:
        symbol_yf = symbol.replace(".SH", ".SS") if symbol.endswith(".SH") else symbol
        try:
            ticker = yf.Ticker(symbol_yf)
            history = ticker.history(period="5d")
            if history is None or history.empty or len(history) < 2:
                result[symbol] = None
            else:
                first_close = history["Close"].iloc[0]
                last_close = history["Close"].iloc[-1]
                pct = ((last_close - first_close) / first_close) * 100
                result[symbol] = round(pct, 2)
        except Exception as exc:
            print(f"Failed to fetch price history for {symbol}: {exc}")
            result[symbol] = None

    return result


def generate_portfolio_summary(pnl_data: dict) -> str:
    """Use Gemini to generate a short plain-text portfolio summary."""
    if not _genai_client:
        return "[GEMINI_API_KEY not configured. AI summary unavailable.]"

    rows = []
    for ticker, pct in pnl_data.items():
        pct_str = f"{pct:+.2f}%" if pct is not None else "N/A"
        rows.append(f"- {ticker}: {pct_str}")
    holdings_summary = "\n".join(rows)

    prompt = f"""
You are a portfolio analyst. Summarize this weekly holdings performance in 2 to 4 short sentences.
Focus on overall performance, leaders and laggards, and what deserves attention next week.
Use plain text only.

{holdings_summary}
"""
    response = _genai_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return response.text.strip()


def run_weekly_report(holdings_path: str | None = None):
    """Generate and send the weekly report."""
    if holdings_path is None:
        holdings_path = DEFAULT_HOLDINGS_PATH

    print("Generating weekly position report...")
    print("  [1/3] Calculating weekly PnL...")
    pnl = calculate_weekly_pnl(holdings_path=holdings_path)

    print("  [2/3] Generating AI summary...")
    ai_summary = generate_portfolio_summary(pnl_data=pnl)

    print("  [3/3] Sending report to Telegram...")
    today_str = datetime.now().strftime("%Y-%m-%d")
    lines = [f"Portfolio Weekly Report | {today_str}\n"]
    for ticker, pct in sorted(pnl.items(), key=lambda item: (item[1] or 0), reverse=True):
        if pct is None:
            lines.append(f"  - {ticker}: N/A")
        elif pct > 0:
            lines.append(f"  + {ticker}: {pct:+.2f}%")
        else:
            lines.append(f"  - {ticker}: {pct:+.2f}%")

    lines.append(f"\n*AI Summary*\n{ai_summary}")
    lines.append("\nFor deeper diagnosis, run /position.")

    message = "\n".join(lines)
    send_telegram_message(message)
    print("Weekly report sent.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send the weekly position report.")
    parser.add_argument("--holdings", type=str, default=None, help="Path to holdings.json")
    args = parser.parse_args()

    run_weekly_report(holdings_path=args.holdings)
