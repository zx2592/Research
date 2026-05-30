#!/usr/bin/env python3
"""
Market Sentinel
v3.5

Detect significant market moves and push quick alerts to Telegram.
"""

import os
import sys
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["RUNNING_AS_SENTINEL"] = "1"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.data_manager import DataManager
from core.notifier import send_telegram_message

try:
    from research_cli import ResearchAgent
except ImportError:
    sys.path.insert(0, os.path.dirname(PROJECT_ROOT))
    from research.research_cli import ResearchAgent

CHANGE_THRESHOLD = 4.0
CRYPTO_THRESHOLD = 7.0


def run_sentinel():
    """Run one pass of market anomaly detection and quick analysis."""
    data_manager = DataManager()
    print(f"Market Sentinel started at {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    prices = data_manager.fetch_market_prices()

    alerts = []
    for asset in prices:
        change = abs(asset.get("change", 0))
        threshold = CRYPTO_THRESHOLD if asset.get("type") == "crypto" else CHANGE_THRESHOLD
        if change >= threshold:
            direction = "UP" if asset.get("change", 0) > 0 else "DOWN"
            alerts.append(
                {
                    "name": asset["name"],
                    "ticker": asset["ticker"],
                    "change": asset["change"],
                    "price": asset.get("price", "N/A"),
                    "direction": direction,
                    "type": asset.get("type", "stock"),
                }
            )

    if not alerts:
        print("No significant moves detected.")
        return

    intro_lines = [
        "*Market Sentinel Alert*",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "",
    ]
    for alert in alerts:
        intro_lines.append(
            f"{alert['direction']} | {alert['name']} ({alert['ticker']}) | {alert['change']:+.2f}%"
        )
    intro_lines.append("")
    intro_lines.append("Triggering quick analysis...")
    send_telegram_message("\n".join(intro_lines))
    print(f"Detected {len(alerts)} alerts. Triggering agent analysis...")

    agent = ResearchAgent(llm_mode="vps")
    for alert in alerts:
        print(f"Analyzing {alert['ticker']}...")
        prompt = (
            f"Urgent event: {alert['name']} ({alert['ticker']}) moved {alert['change']:+.2f}% "
            f"and the direction is {alert['direction']}. "
            "Run the standard quick event review workflow, identify the likely driver, and explain "
            "whether this looks like noise, a catalyst, or a trend change."
        )
        try:
            result = agent.run(prompt)
            send_telegram_message(f"*Sentinel Quick Review: {alert['ticker']}*\n\n{result}")
        except Exception as exc:
            error_message = f"Automatic analysis failed for {alert['ticker']}: {exc}"
            print(error_message)
            send_telegram_message(error_message)

    print("Sentinel run completed.")


if __name__ == "__main__":
    run_sentinel()
