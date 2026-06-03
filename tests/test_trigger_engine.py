from datetime import datetime, timedelta
import os

from core.event_log import EventLog
from services.trigger import (
    EarningsUpcomingProvider,
    EarningsUpcomingTriggerRule,
    PriceMoveProvider,
    PriceMoveTriggerRule,
    ScheduleProvider,
    ScheduleSpec,
    ScheduleTriggerRule,
    TriggerEngine,
    TriggerStateStore,
)
from services.trigger.models import WorkflowInvocation


class StubExecutor:
    def __init__(self):
        self.calls = []

    def invoke(self, invocation):
        self.calls.append(invocation)
        return {"ok": True, "workflow": invocation.workflow, "ticker": invocation.ticker}


class FailingExecutor:
    def invoke(self, invocation):
        raise RuntimeError(f"boom:{invocation.workflow}:{invocation.ticker}")


class TestScheduleProvider:
    def test_collects_due_schedule(self):
        provider = ScheduleProvider(
            [
                ScheduleSpec(
                    name="morning_scan",
                    workflow="scan",
                    reason="Morning scan",
                    hour=7,
                    minute=30,
                    weekdays=(1,),
                    cooldown_seconds=3600,
                )
            ]
        )
        now = datetime(2026, 3, 17, 7, 30)  # Tuesday

        events = provider.collect(now=now)

        assert len(events) == 1
        assert events[0].event_type == "schedule.tick"
        assert events[0].payload["workflow"] == "scan"
        assert events[0].dedupe_key.startswith("schedule:morning_scan:")

    def test_skips_when_not_due(self):
        provider = ScheduleProvider(
            [
                ScheduleSpec(
                    name="weekly_position_review",
                    workflow="position",
                    reason="Weekly position review",
                    hour=18,
                    minute=0,
                    weekdays=(4,),
                    cooldown_seconds=3600,
                )
            ]
        )

        events = provider.collect(now=datetime(2026, 3, 17, 18, 0))  # Tuesday

        assert events == []


class TestTriggerStateStore:
    def test_cooldown_blocks_repeated_fire(self, tmp_dir):
        store = TriggerStateStore(path=os.path.join(tmp_dir, "state.json"))
        now = datetime(2026, 3, 17, 7, 30)
        store.mark_fired("schedule:morning_scan:scan", now)

        assert store.should_fire("schedule:morning_scan:scan", now, cooldown_seconds=3600) is False
        assert store.should_fire(
            "schedule:morning_scan:scan",
            now + timedelta(seconds=3601),
            cooldown_seconds=3600,
        ) is True


class TestPriceMoveProvider:
    def test_collects_large_moves(self):
        provider = PriceMoveProvider(
            fetch_prices=lambda: [
                {"ticker": "NVDA", "name": "NVIDIA", "change": 4.2, "price": 901.0},
                {"ticker": "V", "name": "Visa", "change": 1.2, "price": 311.0},
            ],
            threshold_pct=3.5,
        )

        events = provider.collect(now=datetime(2026, 3, 17, 10, 0))

        assert len(events) == 1
        assert events[0].event_type == "price.move"
        assert events[0].symbol == "NVDA"
        assert events[0].payload["change_pct"] == 4.2


class TestEarningsUpcomingProvider:
    def test_collects_near_term_earnings(self, tmp_dir):
        holdings_path = os.path.join(tmp_dir, "holdings.json")
        with open(holdings_path, "w", encoding="utf-8") as handle:
            handle.write('{"tickers": {"NVDA": {}, "V": {}}}')

        now = datetime(2026, 3, 17, 9, 0)
        provider = EarningsUpcomingProvider(
            holdings_path=holdings_path,
            earnings_fetcher=lambda ticker: {
                "NVDA": datetime(2026, 3, 20, 16, 0),
                "V": datetime(2026, 4, 5, 16, 0),
            }.get(ticker),
            lookahead_days=7,
        )

        events = provider.collect(now=now)

        assert len(events) == 1
        assert events[0].event_type == "earnings.upcoming"
        assert events[0].symbol == "NVDA"
        assert events[0].payload["days_left"] == 3


class TestTriggerEngine:
    def test_process_event_invokes_executor_and_logs(self, tmp_dir):
        provider = ScheduleProvider(
            [
                ScheduleSpec(
                    name="morning_scan",
                    workflow="scan",
                    reason="Morning scan",
                    hour=7,
                    minute=30,
                    weekdays=(1,),
                    cooldown_seconds=3600,
                )
            ]
        )
        event = provider.collect(now=datetime(2026, 3, 17, 7, 30))[0]
        executor = StubExecutor()
        event_log = EventLog(log_dir=os.path.join(tmp_dir, "events"))
        store = TriggerStateStore(path=os.path.join(tmp_dir, "state.json"))
        engine = TriggerEngine(
            executor=executor,
            rules=[ScheduleTriggerRule()],
            event_log=event_log,
            state_store=store,
        )

        results = engine.process_event(event)

        assert len(results) == 1
        assert executor.calls[0].workflow == "scan"
        assert event_log.count() == 3
        event_types = [item.event_type for item in event_log.replay()]
        assert event_types == ["trigger.received", "trigger.fired", "trigger.completed"]

    def test_process_event_respects_cooldown(self, tmp_dir):
        provider = ScheduleProvider(
            [
                ScheduleSpec(
                    name="morning_scan",
                    workflow="scan",
                    reason="Morning scan",
                    hour=7,
                    minute=30,
                    weekdays=(1,),
                    cooldown_seconds=3600,
                )
            ]
        )
        event = provider.collect(now=datetime(2026, 3, 17, 7, 30))[0]
        executor = StubExecutor()
        event_log = EventLog(log_dir=os.path.join(tmp_dir, "events"))
        store = TriggerStateStore(path=os.path.join(tmp_dir, "state.json"))
        engine = TriggerEngine(
            executor=executor,
            rules=[ScheduleTriggerRule()],
            event_log=event_log,
            state_store=store,
        )

        engine.process_event(event)
        results = engine.process_event(event)

        assert results == []
        assert len(executor.calls) == 1
        event_types = [item.event_type for item in event_log.replay()]
        assert event_types[-1] == "trigger.skipped"

    def test_price_move_rule_routes_to_quick(self, tmp_dir):
        event = PriceMoveProvider(
            fetch_prices=lambda: [{"ticker": "NVDA", "name": "NVIDIA", "change": 5.1, "price": 902.0}],
            threshold_pct=3.5,
        ).collect(now=datetime(2026, 3, 17, 10, 0))[0]
        executor = StubExecutor()
        engine = TriggerEngine(
            executor=executor,
            rules=[PriceMoveTriggerRule()],
            event_log=EventLog(log_dir=os.path.join(tmp_dir, "events")),
            state_store=TriggerStateStore(path=os.path.join(tmp_dir, "state.json")),
        )

        results = engine.process_event(event)

        assert len(results) == 1
        assert executor.calls[0].workflow == "quick"
        assert executor.calls[0].ticker == "NVDA"

    def test_earnings_rule_routes_to_update(self, tmp_dir):
        holdings_path = os.path.join(tmp_dir, "holdings.json")
        with open(holdings_path, "w", encoding="utf-8") as handle:
            handle.write('{"tickers": {"NVDA": {}}}')
        event = EarningsUpcomingProvider(
            holdings_path=holdings_path,
            earnings_fetcher=lambda ticker: datetime(2026, 3, 19, 16, 0),
            lookahead_days=7,
        ).collect(now=datetime(2026, 3, 17, 9, 0))[0]
        executor = StubExecutor()
        engine = TriggerEngine(
            executor=executor,
            rules=[EarningsUpcomingTriggerRule()],
            event_log=EventLog(log_dir=os.path.join(tmp_dir, "events")),
            state_store=TriggerStateStore(path=os.path.join(tmp_dir, "state.json")),
        )

        results = engine.process_event(event)

        assert len(results) == 1
        assert executor.calls[0].workflow == "update"
        assert executor.calls[0].ticker == "NVDA"
