from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Dict

from filelock import FileLock

logger = logging.getLogger(__name__)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class TriggerStateStore:
    """Persistent cooldown store keyed by invocation dedupe_key."""

    def __init__(self, path: str = "data/trigger/state.json"):
        self.path = path
        self._lock = FileLock(self.path + ".lock")

    def _load(self) -> Dict[str, str]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Trigger state 文件损坏，返回空状态: %s", e)
            return {}

    def _save(self, state: Dict[str, str]) -> None:
        dir_name = os.path.dirname(self.path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name or ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp_path, self.path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def last_fired_at(self, dedupe_key: str) -> datetime | None:
        with self._lock:
            state = self._load()
        value = state.get(dedupe_key)
        if not value:
            return None
        return datetime.fromisoformat(value)

    def should_fire(self, dedupe_key: str, now: datetime, cooldown_seconds: int) -> bool:
        if cooldown_seconds <= 0:
            return True
        with self._lock:
            last_fired = self._load().get(dedupe_key)
        if last_fired is None:
            return True
        last_dt = datetime.fromisoformat(last_fired)
        return _to_utc(now) >= _to_utc(last_dt) + timedelta(seconds=cooldown_seconds)

    def mark_fired(self, dedupe_key: str, fired_at: datetime) -> None:
        with self._lock:
            state = self._load()
            state[dedupe_key] = _to_utc(fired_at).isoformat()
            self._save(state)
