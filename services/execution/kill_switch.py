"""
KillSwitch — 紧急熔断开关

A persistent on/off switch that blocks all trade execution when activated.
State is stored to disk so it survives restarts.
Uses file locking and atomic writes for concurrency safety.
"""
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from filelock import FileLock

logger = logging.getLogger(__name__)


class KillSwitch:
    """Persistent emergency stop for trading."""

    def __init__(self, state_path: str = "data/execution/kill_switch.json"):
        self.state_path = state_path
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        self._lock = FileLock(self.state_path + ".lock")

    def _read_state_unlocked(self) -> dict:
        """Read state without acquiring lock (caller must hold lock)."""
        if not os.path.exists(self.state_path):
            return {"active": False}
        with open(self.state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _read_state(self) -> dict:
        with self._lock:
            return self._read_state_unlocked()

    def _write_state(self, state: dict) -> None:
        with self._lock:
            self._write_state_unlocked(state)

    def _write_state_unlocked(self, state: dict) -> None:
        """Atomic write via tempfile + os.replace (caller must hold lock)."""
        dir_name = os.path.dirname(self.state_path) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.state_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def is_active(self) -> bool:
        """Returns True if the kill switch is engaged."""
        return self._read_state().get("active", False)

    def activate(self, reason: str = "") -> None:
        """Engage the kill switch — blocks all new orders."""
        self._write_state({
            "active": True,
            "reason": reason,
            "activated_at": datetime.now(timezone.utc).isoformat(),
        })

    def deactivate(self) -> None:
        """Disengage the kill switch — allows trading to resume."""
        self._write_state({
            "active": False,
            "deactivated_at": datetime.now(timezone.utc).isoformat(),
        })

    def status(self) -> dict:
        """Return full kill switch state dict."""
        return self._read_state()

    @contextmanager
    def check_and_hold(self):
        """检查状态并持有锁，直到上下文退出。供 Pipeline 使用。"""
        with self._lock:
            state = self._read_state_unlocked()
            yield state.get("active", False), state.get("reason", "")
