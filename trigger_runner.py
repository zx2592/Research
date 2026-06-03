#!/usr/bin/env python3
"""Trigger Engine runner for proactive workflow execution."""

from __future__ import annotations

import argparse
from datetime import datetime

from services.trigger import (
    run_trigger_cycle,
    serve_trigger_loop,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Trigger Engine runner")
    parser.add_argument(
        "--now",
        type=str,
        default=None,
        help="Override current time in ISO format for testing.",
    )
    parser.add_argument(
        "--schedule",
        type=str,
        default=None,
        help="Run only one named default schedule.",
    )
    parser.add_argument(
        "--disable-schedule",
        action="store_true",
        help="Disable schedule-based triggers for this run.",
    )
    parser.add_argument(
        "--disable-price",
        action="store_true",
        help="Disable price-move triggers for this run.",
    )
    parser.add_argument(
        "--disable-earnings",
        action="store_true",
        help="Disable earnings triggers for this run.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep running and poll for trigger events continuously.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=60,
        help="Polling interval in seconds when --loop is enabled.",
    )
    args = parser.parse_args()

    if args.loop:
        serve_trigger_loop(
            poll_seconds=args.poll_seconds,
            disable_schedule=args.disable_schedule,
            disable_price=args.disable_price,
            disable_earnings=args.disable_earnings,
        )
        return

    now = datetime.fromisoformat(args.now) if args.now else datetime.now()
    messages = run_trigger_cycle(
        now=now,
        schedule=args.schedule,
        disable_schedule=args.disable_schedule,
        disable_price=args.disable_price,
        disable_earnings=args.disable_earnings,
    )
    if not messages:
        print("No triggers due.")
        return
    for message in messages:
        print(message)


if __name__ == "__main__":
    main()
