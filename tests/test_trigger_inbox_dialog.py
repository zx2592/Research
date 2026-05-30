import os

from services.trigger import IDETriggerInboxService, TriggerInboxService
from services.trigger.models import WorkflowInvocation


class TestTriggerInboxDialog:
    def test_view_uses_timeline_summary(self, tmp_dir):
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
                metadata={"event_type": "price.move", "change_pct": 4.2, "direction": "up"},
            )
        )

        payload = ide.view()

        assert payload["counts"]["active"] == 1
        assert payload["items"][0]["headline"] == "NVDA 异动 +4.20% (up) -> quick"
        assert payload["timeline"][0].endswith("NVDA 异动 +4.20% (up) -> quick")
        assert "Trigger inbox 当前显示 1 项。" in payload["summary"]

    def test_get_notification_returns_proactive_reply_block(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        item = inbox.enqueue(
            WorkflowInvocation(
                workflow="scan",
                reason="Run the scheduled morning market scan.",
                dedupe_key="schedule:morning_scan:1",
                metadata={"event_type": "schedule.tick", "schedule_name": "morning_scan"},
            )
        )

        payload = ide.get_notification(item["item_id"])

        assert payload["item"]["item_id"] == item["item_id"]
        assert "[Trigger Inbox]" in payload["summary"]
        assert "定时任务 morning_scan -> scan" in payload["summary"]
        assert f"开始 {item['item_id']}" in payload["summary"]

    def test_handle_message_view_without_inbox_keyword(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        inbox.enqueue(
            WorkflowInvocation(
                workflow="update",
                ticker="META",
                reason="Run update on META.",
                dedupe_key="earnings_upcoming:META",
            )
        )

        payload = ide.handle_message("查看", actor="codex")

        assert payload["intent"] == "view"
        assert payload["items"][0]["ticker"] == "META"

    def test_handle_message_ignore_in_chinese(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        item = inbox.enqueue(
            WorkflowInvocation(
                workflow="scan",
                reason="Morning scan.",
                dedupe_key="schedule:scan:3",
            )
        )

        payload = ide.handle_message(f"忽略 {item['item_id']} 暂不处理", actor="codex")

        assert payload["intent"] == "ignore_item"
        assert inbox.get_item(item["item_id"])["status"] == "ignored"
        assert inbox.get_item(item["item_id"])["result"]["note"] == "暂不处理"

    def test_handle_message_ignore_with_mojibake_alias(self, tmp_dir):
        inbox = TriggerInboxService(
            queue_path=os.path.join(tmp_dir, "desktop_queue.jsonl"),
            state_path=os.path.join(tmp_dir, "inbox_state.json"),
        )
        ide = IDETriggerInboxService(inbox)
        item = inbox.enqueue(
            WorkflowInvocation(
                workflow="scan",
                reason="Morning scan.",
                dedupe_key="schedule:scan:4",
            )
        )

        payload = ide.handle_message(f"蹇界暐 {item['item_id']} 鏆備笉澶勭悊", actor="codex")

        assert payload["intent"] == "ignore_item"
        assert inbox.get_item(item["item_id"])["status"] == "ignored"
