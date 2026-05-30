from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Iterable

from filelock import FileLock

from core.event_log import Event, EventLog

from .models import WorkflowInvocation

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = {"pending", "claimed", "running"}
TERMINAL_STATUSES = {"completed", "ignored", "failed"}
VALID_STATUSES = ACTIVE_STATUSES | TERMINAL_STATUSES


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _normalize_iso_timestamp(value: str | None) -> str:
    if not value:
        return _utc_now().isoformat()
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


def _legacy_item_id(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"legacy-{digest}"


def _build_timestamp_item_id(created_at_iso: str, existing_ids: Iterable[str]) -> str:
    dt = datetime.fromisoformat(created_at_iso)
    stem = dt.strftime("%Y%m%d-%H%M%S")
    prefix = f"{stem}-"
    max_sequence = 0
    for item_id in existing_ids:
        if not item_id.startswith(prefix):
            continue
        suffix = item_id[len(prefix):]
        if suffix.isdigit():
            max_sequence = max(max_sequence, int(suffix))
    return f"{stem}-{max_sequence + 1:03d}"


class TriggerInboxService:
    """Stateful inbox for queued trigger invocations."""

    def __init__(
        self,
        queue_path: str = "data/trigger/desktop_queue.jsonl",
        state_path: str | None = None,
        event_log: EventLog | None = None,
    ):
        self.queue_path = queue_path
        self.state_path = state_path or os.path.join(os.path.dirname(queue_path), "inbox_state.json")
        self._lock = FileLock(self.state_path + ".lock")
        self.event_log = event_log or EventLog(
            log_dir=os.path.join(os.path.dirname(self.state_path), "event_log"),
            filename="trigger_inbox.jsonl",
        )

    def enqueue(self, invocation: WorkflowInvocation, source: str = "trigger.desktop_executor") -> dict[str, Any]:
        now = _utc_now().isoformat()
        with self._lock:
            items = self._load_items()
            item = {
                "item_id": _build_timestamp_item_id(now, items.keys()),
                "status": "pending",
                "created_at": now,
                "updated_at": now,
                "queued_at": now,
                "workflow": invocation.workflow,
                "ticker": invocation.ticker,
                "reason": invocation.reason,
                "dedupe_key": invocation.dedupe_key,
                "priority": invocation.priority,
                "cooldown_seconds": invocation.cooldown_seconds,
                "delivery": list(invocation.delivery),
                "metadata": dict(invocation.metadata),
                "source": source,
                "attempts": 0,
                "claimed_by": None,
                "claimed_at": None,
                "started_at": None,
                "completed_at": None,
                "ignored_at": None,
                "failed_at": None,
                "result": None,
                "error": None,
            }
            self._append_queue_row(item)
            items[item["item_id"]] = item
            self._save_items(items)
        self._emit_event("trigger.inbox.queued", item)
        return dict(item)

    def list_items(
        self,
        status: str | Iterable[str] | None = None,
        include_terminal: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        items = list(self._load_items().values())
        allowed_statuses = self._coerce_statuses(status)
        if allowed_statuses is not None:
            items = [item for item in items if item["status"] in allowed_statuses]
        elif not include_terminal:
            items = [item for item in items if item["status"] in ACTIVE_STATUSES]
        items.sort(
            key=lambda item: (
                item["status"] not in ACTIVE_STATUSES,
                int(item.get("priority", 100) or 100),
                item["created_at"],
                item["item_id"],
            )
        )
        if limit is not None:
            items = items[:limit]
        return [dict(item) for item in items]

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        item = self._load_items().get(item_id)
        return dict(item) if item else None

    def claim_item(self, item_id: str, actor: str = "ide") -> dict[str, Any]:
        return self._transition_item(
            item_id,
            allowed_statuses={"pending", "claimed"},
            next_status="claimed",
            actor=actor,
            extra_updates={"claimed_by": actor, "claimed_at": _utc_now().isoformat()},
            event_type="trigger.inbox.claimed",
        )

    def start_item(self, item_id: str, actor: str = "ide") -> dict[str, Any]:
        item = self._load_required_item(item_id)
        if item["status"] == "pending":
            item = self.claim_item(item_id, actor=actor)
        elif item["status"] == "claimed" and item.get("claimed_by") not in (None, actor):
            raise ValueError(f"Item {item_id} is already claimed by {item['claimed_by']}")
        return self._transition_item(
            item_id,
            allowed_statuses={"claimed", "running"},
            next_status="running",
            actor=actor,
            extra_updates={
                "claimed_by": actor,
                "claimed_at": item.get("claimed_at") or _utc_now().isoformat(),
                "started_at": _utc_now().isoformat(),
                "attempts": int(item.get("attempts", 0) or 0) + 1,
                "error": None,
            },
            event_type="trigger.inbox.running",
        )

    def complete_item(self, item_id: str, actor: str = "ide", result: Any = None) -> dict[str, Any]:
        return self._transition_item(
            item_id,
            allowed_statuses=ACTIVE_STATUSES,
            next_status="completed",
            actor=actor,
            extra_updates={
                "claimed_by": actor,
                "completed_at": _utc_now().isoformat(),
                "result": result,
                "error": None,
            },
            event_type="trigger.inbox.completed",
        )

    def ignore_item(self, item_id: str, actor: str = "ide", note: str | None = None) -> dict[str, Any]:
        return self._transition_item(
            item_id,
            allowed_statuses=ACTIVE_STATUSES,
            next_status="ignored",
            actor=actor,
            extra_updates={
                "claimed_by": actor,
                "ignored_at": _utc_now().isoformat(),
                "result": {"note": note} if note else None,
            },
            event_type="trigger.inbox.ignored",
        )

    def fail_item(self, item_id: str, actor: str = "ide", error: str | None = None) -> dict[str, Any]:
        return self._transition_item(
            item_id,
            allowed_statuses=ACTIVE_STATUSES,
            next_status="failed",
            actor=actor,
            extra_updates={
                "claimed_by": actor,
                "failed_at": _utc_now().isoformat(),
                "error": error,
            },
            event_type="trigger.inbox.failed",
        )

    def execute_item(self, item_id: str, executor, actor: str = "ide") -> dict[str, Any]:
        item = self.start_item(item_id, actor=actor)
        invocation = self._item_to_invocation(item)
        try:
            result = executor.invoke(invocation)
        except Exception as exc:
            self.fail_item(item_id, actor=actor, error=str(exc))
            raise
        completed_item = self.complete_item(item_id, actor=actor, result=result)
        return {
            "status": completed_item["status"],
            "item_id": item_id,
            "workflow": completed_item["workflow"],
            "ticker": completed_item["ticker"],
            "result": result,
        }

    def _load_items(self) -> dict[str, dict[str, Any]]:
        items: dict[str, dict[str, Any]] = {}
        if os.path.exists(self.state_path):
            with open(self.state_path, "r", encoding="utf-8") as handle:
                raw_state = json.load(handle)
            for raw_item in raw_state.get("items", []):
                normalized = self._normalize_item(raw_item)
                items[normalized["item_id"]] = normalized

        imported = False
        for queued_item in self._read_queue_rows():
            if queued_item["item_id"] not in items:
                items[queued_item["item_id"]] = queued_item
                imported = True

        if imported or (not os.path.exists(self.state_path) and items):
            self._save_items(items)
        return items

    def _save_items(self, items: dict[str, dict[str, Any]]) -> None:
        _ensure_parent_dir(self.state_path)
        payload = {
            "version": 1,
            "items": [
                items[item_id]
                for item_id in sorted(
                    items,
                    key=lambda key: (items[key]["created_at"], key),
                )
            ],
        }
        dir_name = os.path.dirname(self.state_path) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp_path, self.state_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _append_queue_row(self, item: dict[str, Any]) -> None:
        _ensure_parent_dir(self.queue_path)
        with open(self.queue_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _read_queue_rows(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.queue_path):
            return []
        rows: list[dict[str, Any]] = []
        with open(self.queue_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rows.append(self._normalize_item(json.loads(line)))
        return rows

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        legacy_seed = {
            "queued_at": normalized.get("queued_at"),
            "workflow": normalized.get("workflow"),
            "ticker": normalized.get("ticker"),
            "reason": normalized.get("reason"),
            "dedupe_key": normalized.get("dedupe_key"),
            "metadata": normalized.get("metadata"),
        }
        created_at = _normalize_iso_timestamp(normalized.get("created_at") or normalized.get("queued_at"))
        normalized["item_id"] = normalized.get("item_id") or _legacy_item_id(legacy_seed)
        normalized["status"] = normalized.get("status") if normalized.get("status") in VALID_STATUSES else "pending"
        normalized["created_at"] = created_at
        normalized["updated_at"] = _normalize_iso_timestamp(normalized.get("updated_at") or created_at)
        normalized["queued_at"] = _normalize_iso_timestamp(normalized.get("queued_at") or created_at)
        normalized["workflow"] = normalized.get("workflow")
        normalized["ticker"] = normalized.get("ticker")
        normalized["reason"] = normalized.get("reason")
        normalized["dedupe_key"] = normalized.get("dedupe_key")
        normalized["priority"] = int(normalized.get("priority", 100) or 100)
        normalized["cooldown_seconds"] = int(normalized.get("cooldown_seconds", 0) or 0)
        normalized["delivery"] = list(normalized.get("delivery") or ["event_log"])
        normalized["metadata"] = dict(normalized.get("metadata") or {})
        normalized["source"] = normalized.get("source") or "trigger.desktop_executor"
        normalized["attempts"] = int(normalized.get("attempts", 0) or 0)
        normalized["claimed_by"] = normalized.get("claimed_by")
        normalized["claimed_at"] = normalized.get("claimed_at")
        normalized["started_at"] = normalized.get("started_at")
        normalized["completed_at"] = normalized.get("completed_at")
        normalized["ignored_at"] = normalized.get("ignored_at")
        normalized["failed_at"] = normalized.get("failed_at")
        normalized["result"] = normalized.get("result")
        normalized["error"] = normalized.get("error")
        return normalized

    def _coerce_statuses(self, status: str | Iterable[str] | None) -> set[str] | None:
        if status is None:
            return None
        if isinstance(status, str):
            return {status}
        return {item for item in status}

    def _load_required_item(self, item_id: str) -> dict[str, Any]:
        item = self._load_items().get(item_id)
        if item is None:
            raise KeyError(f"Unknown inbox item: {item_id}")
        return item

    def _transition_item(
        self,
        item_id: str,
        allowed_statuses: set[str],
        next_status: str,
        actor: str,
        extra_updates: dict[str, Any] | None,
        event_type: str,
    ) -> dict[str, Any]:
        with self._lock:
            items = self._load_items()
            item = items.get(item_id)
            if item is None:
                raise KeyError(f"Unknown inbox item: {item_id}")
            if item["status"] not in allowed_statuses:
                raise ValueError(f"Item {item_id} cannot transition from {item['status']} to {next_status}")
            claimed_by = item.get("claimed_by")
            if claimed_by not in (None, actor) and item["status"] in {"claimed", "running"}:
                raise ValueError(f"Item {item_id} is already claimed by {claimed_by}")

            updated = dict(item)
            updated["status"] = next_status
            updated["updated_at"] = _utc_now().isoformat()
            if extra_updates:
                updated.update(extra_updates)
            items[item_id] = self._normalize_item(updated)
            self._save_items(items)
        self._emit_event(event_type, items[item_id], actor=actor)
        return dict(items[item_id])

    def _emit_event(self, event_type: str, item: dict[str, Any], actor: str | None = None) -> None:
        self.event_log.emit(
            Event(
                event_type=event_type,
                source="trigger.inbox",
                payload={
                    "item_id": item["item_id"],
                    "status": item["status"],
                    "workflow": item["workflow"],
                    "ticker": item["ticker"],
                    "dedupe_key": item["dedupe_key"],
                    "actor": actor,
                },
            )
        )

    def _item_to_invocation(self, item: dict[str, Any]) -> WorkflowInvocation:
        return WorkflowInvocation(
            workflow=item["workflow"],
            ticker=item.get("ticker"),
            reason=item["reason"],
            dedupe_key=item["dedupe_key"],
            priority=int(item.get("priority", 100) or 100),
            cooldown_seconds=int(item.get("cooldown_seconds", 0) or 0),
            delivery=tuple(item.get("delivery") or ["event_log"]),
            metadata=dict(item.get("metadata") or {}),
        )
