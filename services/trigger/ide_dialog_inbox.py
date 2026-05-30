from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

from .inbox import ACTIVE_STATUSES, TriggerInboxService

ITEM_ID_PATTERN = r"[a-z0-9-]{8,32}"
STATUS_ALIASES = {
    "pending": "pending",
    "待处理": "pending",
    "待办": "pending",
    "寰呭鐞": "pending",
    "寰呭姙": "pending",
    "claimed": "claimed",
    "已认领": "claimed",
    "宸茶棰": "claimed",
    "running": "running",
    "执行中": "running",
    "处理中": "running",
    "鎵ц涓": "running",
    "澶勭悊涓": "running",
    "completed": "completed",
    "已完成": "completed",
    "完成": "completed",
    "宸插畬鎴": "completed",
    "瀹屾垚": "completed",
    "ignored": "ignored",
    "已忽略": "ignored",
    "忽略": "ignored",
    "宸插拷鐣": "ignored",
    "蹇界暐": "ignored",
    "failed": "failed",
    "失败": "failed",
    "澶辫触": "failed",
}
STATUS_LABELS = {
    "pending": "待处理",
    "claimed": "已认领",
    "running": "执行中",
    "completed": "已完成",
    "ignored": "已忽略",
    "failed": "失败",
}
VIEW_VERBS = ("查看", "看看", "显示", "列出", "list", "show", "鏌ョ湅", "鐪嬬湅", "鏄剧ず", "鍒楀嚭")
DETAIL_VERBS = ("查看", "show", "detail", "详情", "鏌ョ湅", "璇︽儏")
PICK_NEXT_VERBS = (
    "处理下一个",
    "开始下一个",
    "下一个",
    "pick next",
    "start next",
    "next inbox",
    "澶勭悊涓嬩竴涓",
    "寮€濮嬩笅涓€涓",
    "涓嬩竴涓",
)
BEGIN_VERBS = ("开始", "处理", "执行", "start", "begin", "run", "寮€濮", "澶勭悊", "鎵ц")
COMPLETE_VERBS = ("完成", "标记完成", "complete", "done", "瀹屾垚", "鏍囪瀹屾垚")
IGNORE_VERBS = ("忽略", "ignore", "跳过", "skip", "蹇界暐", "璺宠繃")
FAIL_VERBS = ("失败", "报错", "fail", "error", "澶辫触", "鎶ラ敊")


class IDETriggerInboxService:
    """Conversation-oriented facade over the trigger inbox."""

    def __init__(self, inbox_service: TriggerInboxService | None = None):
        self.inbox_service = inbox_service or TriggerInboxService()

    def view(
        self,
        status: str | Iterable[str] | None = None,
        include_terminal: bool = False,
        limit: int = 10,
    ) -> dict[str, Any]:
        items = self.inbox_service.list_items(
            status=status,
            include_terminal=include_terminal,
            limit=limit,
        )
        presented = [self._present_item(item) for item in items]
        return {
            "counts": self._build_counts(include_terminal=include_terminal),
            "items": presented,
            "summary": self._render_summary(items, include_terminal=include_terminal),
            "timeline": [self._render_timeline_entry(item) for item in items],
        }

    def handle_message(self, message: str, actor: str = "ide") -> dict[str, Any]:
        text = (message or "").strip()
        normalized = re.sub(r"\s+", " ", text.lower())

        if not text:
            return self._reply_error("空指令。可用示例：查看 inbox、处理下一个、完成 <item_id>。")

        if self._looks_like_view(normalized):
            status = self._extract_status(text)
            include_terminal = any(token in normalized for token in ("全部", "历史", "all", "terminal"))
            payload = self.view(status=status, include_terminal=include_terminal)
            payload["intent"] = "view"
            return payload

        item_id = self._extract_item_id(text)

        if self._looks_like_get(normalized) and item_id:
            payload = self.get_item(item_id)
            payload["intent"] = "get_item"
            return payload

        if self._looks_like_pick_next(normalized):
            payload = self.pick_next(actor=actor)
            if payload is None:
                return {"intent": "pick_next", "summary": "当前没有待处理的 trigger inbox 项。", "item": None}
            payload["intent"] = "pick_next"
            return payload

        if self._looks_like_complete(normalized) and item_id:
            payload = self.complete_item(
                item_id,
                actor=actor,
                summary=self._extract_summary(text),
                report_path=self._extract_report_path(text),
            )
            payload["intent"] = "complete_item"
            return payload

        if self._looks_like_ignore(normalized) and item_id:
            payload = self.ignore_item(item_id, actor=actor, note=self._extract_reason_tail(text))
            payload["intent"] = "ignore_item"
            return payload

        if self._looks_like_fail(normalized) and item_id:
            payload = self.fail_item(item_id, actor=actor, error=self._extract_reason_tail(text))
            payload["intent"] = "fail_item"
            return payload

        if self._looks_like_begin(normalized) and item_id:
            payload = self.begin_item(item_id, actor=actor)
            payload["intent"] = "begin_item"
            return payload

        return self._reply_error(
            "未识别的 inbox 指令。可用示例：查看 inbox、查看全部 inbox、处理下一个、开始 <item_id>、完成 <item_id> 报告 <path> 总结 <内容>。"
        )

    def get_item(self, item_id: str) -> dict[str, Any]:
        item = self.inbox_service.get_item(item_id)
        if item is None:
            raise KeyError(f"Unknown inbox item: {item_id}")
        return {
            "item": self._present_item(item),
            "summary": self._render_item_detail(item),
        }

    def pick_next(self, actor: str = "ide") -> dict[str, Any] | None:
        items = self.inbox_service.list_items(status="pending", limit=1)
        if not items:
            return None
        return self.begin_item(items[0]["item_id"], actor=actor)

    def begin_item(self, item_id: str, actor: str = "ide") -> dict[str, Any]:
        item = self.inbox_service.start_item(item_id, actor=actor)
        execution_request = self._build_execution_request(item)
        return {
            "item": self._present_item(item),
            "execution_request": execution_request,
            "summary": f"已开始处理 {item['item_id']}：{self._render_event_headline(item)}",
        }

    def complete_item(
        self,
        item_id: str,
        actor: str = "ide",
        summary: str | None = None,
        report_path: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(result or {})
        if summary:
            payload["summary"] = summary
        if report_path:
            payload["report_path"] = report_path
        item = self.inbox_service.complete_item(item_id, actor=actor, result=payload or None)
        return {
            "item": self._present_item(item),
            "summary": self._render_status_summary(item),
        }

    def ignore_item(self, item_id: str, actor: str = "ide", note: str | None = None) -> dict[str, Any]:
        item = self.inbox_service.ignore_item(item_id, actor=actor, note=note)
        return {
            "item": self._present_item(item),
            "summary": self._render_status_summary(item),
        }

    def fail_item(self, item_id: str, actor: str = "ide", error: str | None = None) -> dict[str, Any]:
        item = self.inbox_service.fail_item(item_id, actor=actor, error=error)
        return {
            "item": self._present_item(item),
            "summary": self._render_status_summary(item),
        }

    def get_notification(self, item_id: str) -> dict[str, Any]:
        item = self.inbox_service.get_item(item_id)
        if item is None:
            raise KeyError(f"Unknown inbox item: {item_id}")
        return {
            "item": self._present_item(item),
            "summary": self._render_proactive_summary(item),
        }

    def _build_counts(self, include_terminal: bool) -> dict[str, int]:
        items = self.inbox_service.list_items(include_terminal=True, limit=None)
        counts = {"total": len(items)}
        for item in items:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        if not include_terminal:
            counts["active"] = sum(counts.get(status, 0) for status in ACTIVE_STATUSES)
        return counts

    def _present_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "item_id": item["item_id"],
            "status": item["status"],
            "status_label": STATUS_LABELS.get(item["status"], item["status"]),
            "workflow": item["workflow"],
            "ticker": item.get("ticker"),
            "priority": item.get("priority", 100),
            "reason": item["reason"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
            "claimed_by": item.get("claimed_by"),
            "attempts": item.get("attempts", 0),
            "metadata": dict(item.get("metadata") or {}),
            "result": item.get("result"),
            "error": item.get("error"),
            "headline": self._render_event_headline(item),
            "timeline_entry": self._render_timeline_entry(item),
        }

    def _build_execution_request(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "item_id": item["item_id"],
            "workflow": item["workflow"],
            "ticker": item.get("ticker"),
            "task": item["reason"],
            "source": "trigger_inbox",
            "dedupe_key": item["dedupe_key"],
            "metadata": dict(item.get("metadata") or {}),
            "suggested_prompt": self._build_suggested_prompt(item),
        }

    def _build_suggested_prompt(self, item: dict[str, Any]) -> str:
        if item.get("ticker"):
            return (
                f"执行 workflow `{item['workflow']}`，标的 `{item['ticker']}`。"
                f"触发原因：{item['reason']}。"
                f"完成后把结果回写到 trigger inbox 项 `{item['item_id']}`。"
            )
        return (
            f"执行 workflow `{item['workflow']}`。"
            f"触发原因：{item['reason']}。"
            f"完成后把结果回写到 trigger inbox 项 `{item['item_id']}`。"
        )

    def _render_summary(self, items: list[dict[str, Any]], include_terminal: bool) -> str:
        if not items:
            if include_terminal:
                return "Trigger inbox 为空。"
            return "Trigger inbox 当前没有活跃项。"
        lines = [f"Trigger inbox 当前显示 {len(items)} 项。"]
        lines.extend(self._render_timeline_entry(item) for item in items)
        return "\n".join(lines)

    def _render_item_detail(self, item: dict[str, Any]) -> str:
        lines = [
            self._render_timeline_entry(item),
            f"item_id: {item['item_id']}",
            f"原因: {item['reason']}",
        ]
        if item.get("claimed_by"):
            lines.append(f"认领者: {item['claimed_by']}")
        if item.get("result"):
            lines.append(f"结果: {item['result']}")
        if item.get("error"):
            lines.append(f"错误: {item['error']}")
        return "\n".join(lines)

    def _render_event_headline(self, item: dict[str, Any]) -> str:
        metadata = dict(item.get("metadata") or {})
        event_type = metadata.get("event_type")
        ticker = item.get("ticker")
        workflow = item["workflow"]
        if event_type == "schedule.tick":
            schedule_name = metadata.get("schedule_name") or "unnamed"
            return f"定时任务 {schedule_name} -> {workflow}"
        if event_type == "price.move":
            change_pct = metadata.get("change_pct")
            direction = metadata.get("direction")
            if ticker and change_pct is not None:
                return f"{ticker} 异动 {change_pct:+.2f}% ({direction}) -> {workflow}"
        if event_type == "earnings.upcoming":
            days_left = metadata.get("days_left")
            if ticker and days_left is not None:
                return f"{ticker} 财报临近 {days_left} 天 -> {workflow}"
        if ticker:
            return f"{ticker} -> {workflow}"
        return workflow

    def _render_timeline_entry(self, item: dict[str, Any]) -> str:
        time_label = self._format_time(item["created_at"])
        status_label = STATUS_LABELS.get(item["status"], item["status"])
        return f"{time_label} | {status_label} | {self._render_event_headline(item)}"

    def _render_status_summary(self, item: dict[str, Any]) -> str:
        return f"{self._render_timeline_entry(item)} | {item['item_id']}"

    def _render_proactive_summary(self, item: dict[str, Any]) -> str:
        lines = [
            "[Trigger Inbox]",
            self._render_timeline_entry(item),
            f"ID: {item['item_id']}",
            f"原因: {item['reason']}",
            "可直接回复：",
            f"开始 {item['item_id']}",
            f"忽略 {item['item_id']} 暂不处理",
        ]
        return "\n".join(lines)

    def _reply_error(self, summary: str) -> dict[str, Any]:
        return {"intent": "unknown", "summary": summary, "items": []}

    def _looks_like_view(self, normalized: str) -> bool:
        has_view_verb = any(token in normalized for token in VIEW_VERBS)
        return (
            (has_view_verb and "inbox" in normalized)
            or "待办" in normalized
            or "寰呭姙" in normalized
            or normalized in {"查看", "看看", "show", "list"}
        )

    def _looks_like_get(self, normalized: str) -> bool:
        return any(token in normalized for token in DETAIL_VERBS)

    def _looks_like_pick_next(self, normalized: str) -> bool:
        return any(token in normalized for token in PICK_NEXT_VERBS)

    def _looks_like_begin(self, normalized: str) -> bool:
        return any(token in normalized for token in BEGIN_VERBS)

    def _looks_like_complete(self, normalized: str) -> bool:
        return any(token in normalized for token in COMPLETE_VERBS)

    def _looks_like_ignore(self, normalized: str) -> bool:
        return any(token in normalized for token in IGNORE_VERBS)

    def _looks_like_fail(self, normalized: str) -> bool:
        return any(token in normalized for token in FAIL_VERBS)

    def _extract_status(self, text: str) -> str | None:
        normalized = text.lower()
        for token, status in STATUS_ALIASES.items():
            if token.lower() in normalized:
                return status
        return None

    def _extract_item_id(self, text: str) -> str | None:
        match = re.search(ITEM_ID_PATTERN, text.lower())
        return match.group(0) if match else None

    def _extract_report_path(self, text: str) -> str | None:
        match = re.search(r"(?:报告|report)\s+(\S+)", text, flags=re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_summary(self, text: str) -> str | None:
        match = re.search(r"(?:总结|摘要|summary)\s+(.+?)(?=(?:\s+(?:报告|report)\s+\S+)?$)", text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _extract_reason_tail(self, text: str) -> str | None:
        stripped = re.sub(ITEM_ID_PATTERN, "", text, count=1, flags=re.IGNORECASE)
        stripped = re.sub(
            r"(ignore|skip|fail|error|忽略|跳过|失败|报错|蹇界暐|璺宠繃|澶辫触|鎶ラ敊)",
            "",
            stripped,
            flags=re.IGNORECASE,
        )
        stripped = stripped.strip(" ：:，,")
        return stripped or None

    def _format_time(self, value: str) -> str:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%m-%d %H:%M")
