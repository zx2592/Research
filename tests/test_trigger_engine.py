from datetime import datetime, timedelta
import os
import json

from core.event_log import EventLog
from services.trigger import (
    DesktopQueueWorkflowExecutor,
    EarningsUpcomingProvider,
    EarningsUpcomingTriggerRule,
    IDETriggerInboxService,
    PriceMoveProvider,
    PriceMoveTriggerRule,
    ScheduleProvider,
    ScheduleSpec,
    ScheduleTriggerRule,
    TriggerInboxService,
    TriggerEngine,
    TriggerStateStore,
    build_workflow_executor,
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


class TestExecutors:
    def test_desktop_executor_queues_invocation(self, tmp_dir):
        queue_path = os.path.join(tmp_dir, "desktop_queue.jsonl")
        executor = DesktopQueueWorkflowExecutor(queue_path=queue_path)

        result = executor.invoke(
            WorkflowInvocation(
                workflow="quick",
                ticker="NVDA",
                reason="Price move detected.",
                dedupe_key="price_move:NVDA:up",
            )
        )

        assert result["status"] == "queued"
        with open(queue_path, "r", encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        assert len(rows) == 1
        assert rows[0]["item_id"] == result["item_id"]
        assert rows[0]["item_id"].count("-") == 2
        assert len(rows[0]["item_id"].split("-")[-1]) == 3
        assert rows[0]["status"] == "pending"
        assert rows[0]["workflow"] == "quick"
        assert rows[0]["ticker"] == "NVDA"

    def test_build_workflow_executor_desktop(self):
        executor = build_workflow_executor(mode="desktop")
        assert isinstance(executor, DesktopQueueWorkflowExecutor)


class TestTriggerInboxService:
    def test_imports_legacy_queue_rows(self, tmp_dir):
        queue_path = os.path.join(tmp_dir, "desktop_queue.jsonl")
        with open(queue_path, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "queued_at": "2026-03-17T00:00:00+00:00",
                        "workflow": "quick",
                        "ticker": "NVDA",
                        "reason": "Legacy queue row",
                        "dedupe_key": "price_move:NVDA:up",
                        "metadata": {"event_type": "price.move"},
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        inbox = TriggerInboxService(
            queue_path=queue_path,
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )

        items = inbox.list_items()

        assert len(items) == 1
        assert items[0]["item_id"].startswith("legacy-")
        assert items[0]["status"] == "pending"
        assert items[0]["workflow"] == "quick"

    def test_execute_item_transitions_to_completed(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        item = inbox.enqueue(
            WorkflowInvocation(
                workflow="update",
                ticker="NVDA",
                reason="Run update.",
                dedupe_key="earnings_upcoming:NVDA",
            )
        )
        executor = StubExecutor()

        result = inbox.execute_item(item["item_id"], executor=executor, actor="ide")
        stored = inbox.get_item(item["item_id"])

        assert result["status"] == "completed"
        assert len(executor.calls) == 1
        assert stored["status"] == "completed"
        assert stored["attempts"] == 1
        assert stored["result"]["workflow"] == "update"

    def test_ignore_and_fail_items(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ignored = inbox.enqueue(
            WorkflowInvocation(
                workflow="quick",
                ticker="NVDA",
                reason="Ignore me.",
                dedupe_key="price_move:NVDA:up",
            )
        )
        failed = inbox.enqueue(
            WorkflowInvocation(
                workflow="update",
                ticker="META",
                reason="This will fail.",
                dedupe_key="earnings_upcoming:META",
            )
        )

        ignored_item = inbox.ignore_item(ignored["item_id"], actor="ide", note="not needed")

        assert ignored_item["status"] == "ignored"
        assert inbox.get_item(ignored["item_id"])["result"] == {"note": "not needed"}

        try:
            inbox.execute_item(failed["item_id"], executor=FailingExecutor(), actor="ide")
        except RuntimeError as exc:
            assert str(exc) == "boom:update:META"
        else:
            raise AssertionError("execute_item should propagate executor errors")

        assert inbox.get_item(failed["item_id"])["status"] == "failed"
        assert inbox.get_item(failed["item_id"])["error"] == "boom:update:META"

    def test_list_items_orders_by_priority_then_time(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        inbox.enqueue(
            WorkflowInvocation(
                workflow="scan",
                reason="Later but higher priority.",
                dedupe_key="schedule:scan:1",
                priority=10,
            )
        )
        inbox.enqueue(
            WorkflowInvocation(
                workflow="quick",
                ticker="NVDA",
                reason="Earlier but lower priority.",
                dedupe_key="price_move:NVDA:up",
                priority=100,
            )
        )

        items = inbox.list_items()

        assert items[0]["workflow"] == "scan"
        assert items[1]["workflow"] == "quick"

    def test_enqueue_item_ids_use_timestamp_sequence(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )

        first = inbox.enqueue(
            WorkflowInvocation(
                workflow="scan",
                reason="First item.",
                dedupe_key="schedule:scan:1",
            )
        )
        second = inbox.enqueue(
            WorkflowInvocation(
                workflow="scan",
                reason="Second item.",
                dedupe_key="schedule:scan:2",
            )
        )

        first_parts = first["item_id"].split("-")
        second_parts = second["item_id"].split("-")

        assert len(first_parts) == 3
        assert len(first_parts[0]) == 8
        assert len(first_parts[1]) == 6
        assert len(first_parts[2]) == 3
        assert second_parts[:2] == first_parts[:2]
        assert int(second_parts[2]) == int(first_parts[2]) + 1


class TestIDETriggerInboxService:
    def test_view_returns_summary_and_counts(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        inbox.enqueue(
            WorkflowInvocation(
                workflow="quick",
                ticker="NVDA",
                reason="Price move detected.",
                dedupe_key="price_move:NVDA:up",
                priority=20,
            )
        )

        payload = ide.view()

        assert payload["counts"]["total"] == 1
        assert payload["counts"]["active"] == 1
        assert payload["items"][0]["workflow"] == "quick"
        assert "Trigger inbox 当前显示 1 项。" in payload["summary"]

    def test_pick_next_starts_item_and_builds_execution_request(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        item = inbox.enqueue(
            WorkflowInvocation(
                workflow="update",
                ticker="META",
                reason="Run a company update on META.",
                dedupe_key="earnings_upcoming:META",
                priority=30,
            )
        )

        payload = ide.pick_next(actor="codex")

        assert payload["item"]["item_id"] == item["item_id"]
        assert payload["item"]["status"] == "running"
        assert payload["execution_request"]["workflow"] == "update"
        assert payload["execution_request"]["ticker"] == "META"
        assert payload["execution_request"]["task"] == "Run a company update on META."
        assert payload["execution_request"]["source"] == "trigger_inbox"
        assert "完成后把结果回写到 trigger inbox 项" in payload["execution_request"]["suggested_prompt"]

    def test_complete_item_persists_report_metadata(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        item = inbox.enqueue(
            WorkflowInvocation(
                workflow="quick",
                ticker="NVDA",
                reason="Run quick review.",
                dedupe_key="price_move:NVDA:up",
            )
        )
        ide.begin_item(item["item_id"], actor="codex")

        payload = ide.complete_item(
            item["item_id"],
            actor="codex",
            summary="Generated quick report.",
            report_path="Reports/20260317/20260317_NVDA_Quick.md",
            result={"report_type": "quick"},
        )

        stored = inbox.get_item(item["item_id"])

        assert payload["item"]["status"] == "completed"
        assert stored["result"]["summary"] == "Generated quick report."
        assert stored["result"]["report_path"] == "Reports/20260317/20260317_NVDA_Quick.md"
        assert stored["result"]["report_type"] == "quick"

    def test_handle_message_views_inbox_in_chinese(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        inbox.enqueue(
            WorkflowInvocation(
                workflow="quick",
                ticker="NVDA",
                reason="Price move detected.",
                dedupe_key="price_move:NVDA:up",
            )
        )

        payload = ide.handle_message("查看 inbox", actor="codex")

        assert payload["intent"] == "view"
        assert payload["items"][0]["ticker"] == "NVDA"
        assert "Trigger inbox 当前显示 1 项。" in payload["summary"]

    def test_handle_message_starts_next_item_in_chinese(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        item = inbox.enqueue(
            WorkflowInvocation(
                workflow="update",
                ticker="META",
                reason="Run update on META.",
                dedupe_key="earnings_upcoming:META",
            )
        )

        payload = ide.handle_message("处理下一个", actor="codex")

        assert payload["intent"] == "pick_next"
        assert payload["item"]["item_id"] == item["item_id"]
        assert payload["item"]["status"] == "running"
        assert payload["execution_request"]["workflow"] == "update"

    def test_handle_message_completes_item_with_report_and_summary(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        item = inbox.enqueue(
            WorkflowInvocation(
                workflow="quick",
                ticker="NVDA",
                reason="Run quick review.",
                dedupe_key="price_move:NVDA:up",
            )
        )
        ide.begin_item(item["item_id"], actor="codex")

        payload = ide.handle_message(
            f"完成 {item['item_id']} 报告 Reports/20260317/20260317_NVDA_Quick.md 总结 已生成快评",
            actor="codex",
        )

        stored = inbox.get_item(item["item_id"])

        assert payload["intent"] == "complete_item"
        assert stored["status"] == "completed"
        assert stored["result"]["report_path"] == "Reports/20260317/20260317_NVDA_Quick.md"
        assert stored["result"]["summary"] == "已生成快评"

    def test_handle_message_ignores_item_with_reason(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        item = inbox.enqueue(
            WorkflowInvocation(
                workflow="scan",
                reason="Morning scan.",
                dedupe_key="schedule:scan:1",
            )
        )

        payload = ide.handle_message(f"忽略 {item['item_id']} 今天不需要", actor="codex")

        assert payload["intent"] == "ignore_item"
        assert inbox.get_item(item["item_id"])["status"] == "ignored"
        assert inbox.get_item(item["item_id"])["result"]["note"] == "今天不需要"

    def test_handle_message_ignore_not_misrouted_by_reason_text(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        item = inbox.enqueue(
            WorkflowInvocation(
                workflow="scan",
                reason="Morning scan.",
                dedupe_key="schedule:scan:2",
            )
        )

        payload = ide.handle_message(f"忽略 {item['item_id']} 暂不处理", actor="codex")

        assert payload["intent"] == "ignore_item"
        assert inbox.get_item(item["item_id"])["status"] == "ignored"
        assert inbox.get_item(item["item_id"])["result"]["note"] == "暂不处理"


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
