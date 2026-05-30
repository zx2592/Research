from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Iterable

from core.data_manager import DataManager
from core import settings

from .engine import TriggerEngine
from .executor import build_workflow_executor
from .ide_dialog_inbox import IDETriggerInboxService
from .provider import EarningsUpcomingProvider, PriceMoveProvider, ScheduleProvider
from .rules import EarningsUpcomingTriggerRule, PriceMoveTriggerRule, ScheduleTriggerRule
from .models import ScheduleSpec, TriggerEvent

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULES = [
    ScheduleSpec(
        name="morning_scan",
        workflow="scan",
        reason="Run the scheduled morning market scan.",
        hour=7,
        minute=30,
        weekdays=(0, 1, 2, 3, 4),
        cooldown_seconds=settings.trigger.morning_scan_cooldown,
    ),
    ScheduleSpec(
        name="weekly_position_review",
        workflow="position",
        reason="Run the scheduled weekly portfolio review.",
        hour=18,
        minute=0,
        weekdays=(4,),
        cooldown_seconds=settings.trigger.position_review_cooldown,
    ),
]


def build_monitor_engine(executor_mode: str = "auto") -> TriggerEngine:
    return TriggerEngine(
        executor=build_workflow_executor(mode=executor_mode),
        rules=[
            ScheduleTriggerRule(),
            PriceMoveTriggerRule(),
            EarningsUpcomingTriggerRule(),
        ],
    )


def collect_trigger_events(
    now: datetime | None = None,
    schedule: str | None = None,
    disable_schedule: bool = False,
    disable_price: bool = False,
    disable_earnings: bool = False,
    data_manager: DataManager | None = None,
    earnings_fetcher=None,
    holdings_path: str | None = None,
) -> list[TriggerEvent]:
    now = now or datetime.now()
    events: list[TriggerEvent] = []

    if not disable_schedule:
        schedules: Iterable[ScheduleSpec] = DEFAULT_SCHEDULES
        if schedule:
            schedules = [spec for spec in DEFAULT_SCHEDULES if spec.name == schedule]
            if not schedules:
                raise SystemExit(f"Unknown schedule: {schedule}")
        events.extend(ScheduleProvider(schedules).collect(now=now))

    data_manager = data_manager or DataManager()
    if not disable_price:
        events.extend(
            PriceMoveProvider(
                fetch_prices=data_manager.fetch_market_prices,
                threshold_pct=settings.trigger.price_move_threshold,
            ).collect(now=now)
        )

    if not disable_earnings:
        if earnings_fetcher is None:
            from scripts.earnings_reminder import get_earnings_date_cached

            earnings_fetcher = get_earnings_date_cached
        if holdings_path is None:
            holdings_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "Config",
                "holdings.json",
            )
        events.extend(
            EarningsUpcomingProvider(
                holdings_path=holdings_path,
                earnings_fetcher=earnings_fetcher,
                lookahead_days=7,
            ).collect(now=now)
        )

    return events


def render_result_messages(
    results: list[dict],
    executor_mode: str,
    ide_inbox: IDETriggerInboxService | None = None,
) -> list[str]:
    messages: list[str] = []
    ide_inbox = ide_inbox or (IDETriggerInboxService() if executor_mode == "desktop" else None)
    for result in results:
        ticker_suffix = f" {result['ticker']}" if result.get("ticker") else ""
        outcome = result.get("result", {})
        if ide_inbox and isinstance(outcome, dict) and outcome.get("status") == "queued" and outcome.get("item_id"):
            notice = ide_inbox.get_notification(outcome["item_id"])
            messages.append(notice["summary"])
        else:
            messages.append(f"Triggered {result['workflow']}{ticker_suffix}")
    return messages


def run_trigger_cycle(
    executor_mode: str = "auto",
    now: datetime | None = None,
    schedule: str | None = None,
    disable_schedule: bool = False,
    disable_price: bool = False,
    disable_earnings: bool = False,
    engine: TriggerEngine | None = None,
    data_manager: DataManager | None = None,
    earnings_fetcher=None,
    holdings_path: str | None = None,
    ide_inbox: IDETriggerInboxService | None = None,
) -> list[str]:
    engine = engine or build_monitor_engine(executor_mode=executor_mode)
    events = collect_trigger_events(
        now=now,
        schedule=schedule,
        disable_schedule=disable_schedule,
        disable_price=disable_price,
        disable_earnings=disable_earnings,
        data_manager=data_manager,
        earnings_fetcher=earnings_fetcher,
        holdings_path=holdings_path,
    )
    if not events:
        return []

    messages: list[str] = []
    for event in events:
        results = engine.process_event(event)
        messages.extend(render_result_messages(results, executor_mode=executor_mode, ide_inbox=ide_inbox))
    return messages


def serve_trigger_loop(
    executor_mode: str = "auto",
    poll_seconds: int = 60,
    disable_schedule: bool = False,
    disable_price: bool = False,
    disable_earnings: bool = False,
) -> None:
    engine = build_monitor_engine(executor_mode=executor_mode)
    ide_inbox = IDETriggerInboxService() if executor_mode == "desktop" else None
    logger.info("Trigger service started. poll_seconds=%d executor=%s", poll_seconds, executor_mode)
    while True:
        now = datetime.now()
        messages = run_trigger_cycle(
            executor_mode=executor_mode,
            now=now,
            disable_schedule=disable_schedule,
            disable_price=disable_price,
            disable_earnings=disable_earnings,
            engine=engine,
            ide_inbox=ide_inbox,
        )
        for message in messages:
            logger.info(message)
        time.sleep(poll_seconds)
