#!/usr/bin/env python3
"""
Morning scan push utility.
v3.5

Extracts a compact morning brief from the latest market scan report.
"""

import argparse
import os
import re
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

from core.notifier import send_telegram_message

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

REPORTS_ROOT = os.path.join(PROJECT_ROOT, "Reports")
MAX_SUMMARY_LEN = 3500


def _find_report_path(reports_root: str, date_str: str) -> str | None:
    """Return the expected report path for a given date if it exists."""
    path = os.path.join(reports_root, date_str, f"{date_str}_Market_Scan.md")
    return path if os.path.exists(path) else None


def extract_summary(report_path: str, max_len: int = MAX_SUMMARY_LEN) -> str:
    """Extract a compact summary from a market scan markdown report."""
    with open(report_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    lines = content.splitlines()
    output_parts = []

    in_header = True
    for line in lines:
        if in_header:
            output_parts.append(line)
            if line and not line.startswith("#") and not line.startswith(">"):
                if line.strip() == "":
                    in_header = False
        else:
            break

    in_section4 = False
    for line in lines:
        if re.match(r"^## 4\\.", line):
            in_section4 = True
        elif in_section4 and re.match(r"^## [^4]", line):
            in_section4 = False
        if in_section4:
            output_parts.append(line)

    in_section6 = False
    risk_lines_collected = 0
    for line in lines:
        if re.match(r"^## 6\\.", line):
            in_section6 = True
            output_parts.append(line)
            continue
        if in_section6:
            if re.match(r"^## [^6]", line):
                break
            if line.strip().startswith("-"):
                output_parts.append(line)
                risk_lines_collected += 1
                if risk_lines_collected >= 3:
                    break

    result = "\n".join(output_parts)
    if len(result) > max_len:
        result = result[:max_len] + "\n\n[Report truncated. See the full markdown report for details.]"
    return result


def run_morning_push(reports_root: str | None = None, date_str: str | None = None):
    """Find today's report, extract a summary, and push it to Telegram."""
    if reports_root is None:
        reports_root = REPORTS_ROOT
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    report_path = _find_report_path(reports_root, date_str)
    if not report_path:
        print(f"Market scan report not found for {date_str}. Run /scan first.")
        return

    print(f"Extracting morning brief from {report_path}")
    summary = extract_summary(report_path)

    header = f"*AlphaSystem Morning Brief | {date_str}*\n\n"
    footer = f"\n\nFull report: Reports/{date_str}/{date_str}_Market_Scan.md"
    message = header + summary + footer

    print("Sending morning brief to Telegram...")
    send_telegram_message(message)
    print("Morning brief sent.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send the morning scan brief.")
    parser.add_argument("--date", type=str, default=None, help="Report date in YYYYMMDD format")
    args = parser.parse_args()

    run_morning_push(date_str=args.date)
