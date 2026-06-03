#!/usr/bin/env python3
"""Persistent trigger monitoring service."""

from __future__ import annotations

import argparse

from services.trigger import serve_trigger_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Persistent Trigger Engine service")
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=60,
        help="Polling interval in seconds.",
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
    args = parser.parse_args()

    serve_trigger_loop(
        poll_seconds=args.poll_seconds,
        disable_schedule=args.disable_schedule,
        disable_price=args.disable_price,
        disable_earnings=args.disable_earnings,
    )


if __name__ == "__main__":
    main()
