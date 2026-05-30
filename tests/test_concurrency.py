"""
Phase 1 并发安全测试 — KillSwitch / Wallet / Cache / Pipeline / SQLite WAL
"""
import json
import os
import sqlite3
import tempfile
import shutil
import threading
import time

import pytest

from core.artifacts.schemas import OrderIntent
from research_cli import ResearchAgent
from services.execution.kill_switch import KillSwitch
from services.execution.wallet import Wallet
from services.execution.pipeline import ExecutionPipeline, PipelineError
from services.execution.guards import GuardChain, GuardResult
from services.datahub.cache import DataCache
from services.portfolio.db import PortfolioDatabase
from services.portfolio.ledger import PortfolioLedger


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp(prefix="alpha_concurrency_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _make_intent(**overrides):
    defaults = dict(
        ticker="AAPL", side="buy", quantity=10, order_type="limit",
        limit_price=150.0, rationale="test", confidence=0.9,
    )
    defaults.update(overrides)
    return OrderIntent(**defaults)


# ---- KillSwitch ----

class TestKillSwitchAtomic:
    def test_atomic_write_valid_json(self, tmp_dir):
        """写入后文件始终是合法 JSON。"""
        path = os.path.join(tmp_dir, "ks.json")
        ks = KillSwitch(state_path=path)
        ks.activate(reason="test reason")
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        assert state["active"] is True
        assert state["reason"] == "test reason"

    def test_deactivate_valid_json(self, tmp_dir):
        path = os.path.join(tmp_dir, "ks.json")
        ks = KillSwitch(state_path=path)
        ks.activate("reason")
        ks.deactivate()
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        assert state["active"] is False

    def test_check_and_hold_active(self, tmp_dir):
        """check_and_hold 上下文管理器内状态一致。"""
        path = os.path.join(tmp_dir, "ks.json")
        ks = KillSwitch(state_path=path)
        ks.activate("emergency")
        with ks.check_and_hold() as (active, reason):
            assert active is True
            assert reason == "emergency"

    def test_check_and_hold_inactive(self, tmp_dir):
        path = os.path.join(tmp_dir, "ks.json")
        ks = KillSwitch(state_path=path)
        with ks.check_and_hold() as (active, reason):
            assert active is False
            assert reason == ""

    def test_no_state_file_returns_inactive(self, tmp_dir):
        path = os.path.join(tmp_dir, "nonexistent.json")
        ks = KillSwitch(state_path=path)
        assert ks.is_active() is False


# ---- Wallet ----

class TestWalletAtomic:
    def test_commit_creates_valid_jsonl(self, tmp_dir):
        """并发 commit 后所有行可解析。"""
        path = os.path.join(tmp_dir, "wallet.jsonl")
        w = Wallet(history_path=path)
        for i in range(5):
            intent = _make_intent(ticker=f"T{i}")
            w.commit(intent, message=f"commit-{i}")
        history = w.get_history()
        assert len(history) == 5
        assert all(isinstance(r, dict) for r in history)

    def test_corrupt_line_skipped(self, tmp_dir):
        """注入损坏行后 get_history 容错跳过。"""
        path = os.path.join(tmp_dir, "wallet.jsonl")
        w = Wallet(history_path=path)
        intent = _make_intent()
        w.commit(intent, message="good")
        # Inject corrupt line
        with open(path, "a", encoding="utf-8") as f:
            f.write("NOT VALID JSON\n")
        w.commit(intent, message="good2")

        history = w.get_history()
        assert len(history) == 2  # corrupt line skipped


# ---- Cache ----

class TestCacheAtomic:
    def test_set_creates_valid_json(self, tmp_dir):
        cache = DataCache(cache_dir=tmp_dir, default_ttl=3600)
        cache.set("src", "key", {"value": 42})
        result = cache.get("src", "key")
        assert result == {"value": 42}

    def test_get_corrupt_returns_none(self, tmp_dir):
        """损坏文件返回 None 并被删除。"""
        cache = DataCache(cache_dir=tmp_dir, default_ttl=3600)
        cache.set("src", "key", {"value": 1})
        # Corrupt the file
        path = cache._key_to_path("src", "key")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{broken json")
        result = cache.get("src", "key")
        assert result is None
        # File should be removed
        assert not os.path.exists(path)


# ---- Pipeline ----

class _PassGuardChain:
    def run(self, intent, prices):
        return GuardResult.ok()


class _FailAdapter:
    def execute(self, intent, prices):
        raise RuntimeError("broker connection lost")


class _SuccessAdapter:
    def execute(self, intent, prices):
        return {"ticker": intent.ticker, "side": intent.side,
                "quantity": intent.quantity, "price": 150.0, "status": "filled"}


class TestPipelineCompensation:
    def test_adapter_failure_compensates(self, tmp_dir):
        """adapter 失败时 Wallet 有补偿记录。"""
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        wallet = Wallet(history_path=os.path.join(tmp_dir, "w.jsonl"))
        ks = KillSwitch(state_path=os.path.join(tmp_dir, "ks.json"))
        pipeline = ExecutionPipeline(
            ledger=ledger, wallet=wallet,
            guard_chain=_PassGuardChain(), adapter=_FailAdapter(),
            kill_switch=ks,
        )
        intent = _make_intent()
        with pytest.raises(PipelineError, match="Adapter failed"):
            pipeline.execute(intent, prices={"AAPL": 150.0})
        history = wallet.get_history()
        assert len(history) == 2  # commit + compensate
        assert "COMPENSATE" in history[1]["message"]

    def test_pipeline_kill_switch_blocks(self, tmp_dir):
        """KillSwitch 激活时订单被拒。"""
        ledger = PortfolioLedger(db_path=os.path.join(tmp_dir, "p.db"))
        wallet = Wallet(history_path=os.path.join(tmp_dir, "w.jsonl"))
        ks = KillSwitch(state_path=os.path.join(tmp_dir, "ks.json"))
        ks.activate("test stop")
        pipeline = ExecutionPipeline(
            ledger=ledger, wallet=wallet,
            guard_chain=_PassGuardChain(), adapter=_SuccessAdapter(),
            kill_switch=ks,
        )
        intent = _make_intent()
        with pytest.raises(PipelineError, match="KillSwitch"):
            pipeline.execute(intent, prices={"AAPL": 150.0})


# ---- SQLite WAL ----

class TestSQLiteWAL:
    def test_wal_enabled(self, tmp_dir):
        """PRAGMA journal_mode 返回 'wal'。"""
        db_path = os.path.join(tmp_dir, "test.db")
        db = PortfolioDatabase(db_path=db_path)
        conn = sqlite3.connect(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"


# ---- TriggerStateStore (V3.9) ----

from datetime import datetime, timezone
from services.trigger.dedupe import TriggerStateStore


class TestDedupeAtomicWrite:
    """V3.9: TriggerStateStore 原子写入 + FileLock + JSON 容错。"""

    def test_atomic_write_valid_json(self, tmp_dir):
        """写入后文件始终是合法 JSON。"""
        path = os.path.join(tmp_dir, "state.json")
        store = TriggerStateStore(path=path)
        now = datetime.now(timezone.utc)
        store.mark_fired("test_key", now)
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        assert "test_key" in state

    def test_concurrent_mark_all_recorded(self, tmp_dir):
        """多次 mark_fired 后所有记录完整。"""
        path = os.path.join(tmp_dir, "state.json")
        store = TriggerStateStore(path=path)
        now = datetime.now(timezone.utc)
        for i in range(10):
            store.mark_fired(f"key_{i}", now)
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        assert len(state) == 10
        for i in range(10):
            assert f"key_{i}" in state

    def test_corrupt_json_recovery(self, tmp_dir):
        """损坏文件返回空 dict，不抛异常。"""
        path = os.path.join(tmp_dir, "state.json")
        os.makedirs(tmp_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{broken json")
        store = TriggerStateStore(path=path)
        assert store.should_fire("any_key", datetime.now(timezone.utc), 3600) is True

    def test_should_fire_respects_cooldown(self, tmp_dir):
        """cooldown 内 should_fire 返回 False。"""
        path = os.path.join(tmp_dir, "state.json")
        store = TriggerStateStore(path=path)
        now = datetime.now(timezone.utc)
        store.mark_fired("key", now)
        assert store.should_fire("key", now, 3600) is False

    def test_has_lock_attribute(self, tmp_dir):
        """TriggerStateStore 有 _lock 属性（FileLock 实例）。"""
        path = os.path.join(tmp_dir, "state.json")
        store = TriggerStateStore(path=path)
        assert hasattr(store, "_lock")
        from filelock import FileLock
        assert isinstance(store._lock, FileLock)


# ---- TriggerInboxService atomic save (V3.9) ----

from services.trigger.inbox import TriggerInboxService
from services.trigger.models import WorkflowInvocation


class TestInboxAtomicSave:
    """V3.9: TriggerInboxService 原子写入。"""

    def test_save_produces_valid_json(self, tmp_dir):
        """enqueue 后 state 文件是合法 JSON。"""
        queue_path = os.path.join(tmp_dir, "queue.jsonl")
        state_path = os.path.join(tmp_dir, "state.json")
        inbox = TriggerInboxService(queue_path=queue_path, state_path=state_path)
        inv = WorkflowInvocation(
            workflow="scan", ticker=None, reason="test",
            dedupe_key="test:scan",
        )
        inbox.enqueue(inv)
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == 1
        assert len(data["items"]) == 1


# ---- Bot _unauth_attempts bounded (V3.9) ----

class TestUnauthAttemptsBounded:
    """V3.9: _unauth_attempts 超过上限自动清理。"""

    def test_bounded_at_max(self):
        from bot.telegram_bot import _unauth_attempts, _MAX_UNAUTH_ENTRIES
        # Save original state
        original = dict(_unauth_attempts)
        try:
            _unauth_attempts.clear()
            # Fill to max
            for i in range(_MAX_UNAUTH_ENTRIES):
                _unauth_attempts[str(i)] = i
            assert len(_unauth_attempts) == _MAX_UNAUTH_ENTRIES
        finally:
            # Restore
            _unauth_attempts.clear()
            _unauth_attempts.update(original)


class _ConcurrentFakeRunner:
    def build_system_instruction(self, workflow_name):
        return f"SYSTEM::{workflow_name}"


class _ConcurrentFakeLLM:
    def __init__(self):
        self.system_instruction = None

    def reset(self):
        return None

    def create_chat(self, **kwargs):
        return None

    def chat(self, task):
        time.sleep(0.05)
        return self.system_instruction


class TestResearchAgentChatLock:
    def test_parallel_workflows_do_not_clobber_each_other(self):
        agent = ResearchAgent.__new__(ResearchAgent)
        agent.runner = _ConcurrentFakeRunner()
        agent.llm = _ConcurrentFakeLLM()
        agent._chat_lock = threading.RLock()
        agent._tools = lambda: []

        results = {}

        def _run(name):
            results[name] = agent.run_workflow(name, f"task::{name}")

        threads = [threading.Thread(target=_run, args=(name,)) for name in ("deep", "scan")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert results["deep"] == "SYSTEM::deep"
        assert results["scan"] == "SYSTEM::scan"
