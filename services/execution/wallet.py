"""
Wallet — 交易意图 commit 历史 (类 Git)

Inspired by OpenAlice's wallet: stage → commit → push.
Every committed OrderIntent gets an 8-char hash and is persisted to JSONL.
Uses file locking for concurrency safety.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from filelock import FileLock

from core.artifacts.schemas import OrderIntent

logger = logging.getLogger(__name__)


class Wallet:
    """Append-only JSONL commit history for order intents."""

    def __init__(self, history_path: str = "data/execution/wallet.jsonl"):
        self.history_path = history_path
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        self._lock = FileLock(self.history_path + ".lock")

    def commit(self, intent: OrderIntent, message: str = "") -> str:
        """
        Record an OrderIntent commit.
        Returns an 8-char commit hash.
        """
        commit_hash = uuid.uuid4().hex[:8]
        record = {
            "commit_hash": commit_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message,
            "intent_id": intent.intent_id,
            "ticker": intent.ticker,
            "side": intent.side,
            "quantity": intent.quantity,
            "order_type": intent.order_type,
            "limit_price": intent.limit_price,
            "rationale": intent.rationale,
            "confidence": intent.confidence,
            "status": intent.status,
        }
        with self._lock:
            with open(self.history_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        return commit_hash

    def get_history(self) -> List[Dict[str, Any]]:
        """Return all commit records in chronological order."""
        if not os.path.exists(self.history_path):
            return []
        records = []
        with open(self.history_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Wallet 历史记录第 %d 行损坏，已跳过", line_num)
        return records
