"""
TDD Tests for core/toolbus/ — ToolBus (工具总线)

Tests written FIRST. Covers:
- ToolRegistry: register/list/get tools
- BudgetManager: per-workflow budget tracking & limits
- EvidenceRecorder: source citation recording
- ToolBus: unified call with budget + evidence + audit
"""
import os
import json
import pytest

from core.toolbus.registry import ToolDefinition, ToolRegistry
from core.toolbus.budget import BudgetManager, BudgetExhaustedError
from core.toolbus.evidence import EvidenceRecorder, SourceRef
from core.toolbus.bus import ToolBus, WorkflowContext
from core.event_log import EventLog


# ── ToolRegistry ─────────────────────────────────────────────────

class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = ToolDefinition(
            name="search_web",
            category="data",
            handler=lambda q: f"results for {q}",
            permission_level=0,
            budget_cost=1,
            description="Search the web",
        )
        reg.register(tool)
        assert reg.get("search_web") is tool

    def test_get_nonexistent_returns_none(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition("a", "data", lambda: None, 0, 1, "tool a"))
        reg.register(ToolDefinition("b", "exec", lambda: None, 2, 5, "tool b"))
        names = reg.list_tools()
        assert set(names) == {"a", "b"}

    def test_list_by_category(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition("a", "data", lambda: None, 0, 1, ""))
        reg.register(ToolDefinition("b", "data", lambda: None, 0, 1, ""))
        reg.register(ToolDefinition("c", "execution", lambda: None, 2, 5, ""))
        data_tools = reg.list_tools(category="data")
        assert set(data_tools) == {"a", "b"}

    def test_duplicate_register_raises(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition("x", "data", lambda: None, 0, 1, ""))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(ToolDefinition("x", "data", lambda: None, 0, 1, ""))

    def test_unregister(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition("x", "data", lambda: None, 0, 1, ""))
        reg.unregister("x")
        assert reg.get("x") is None


# ── BudgetManager ────────────────────────────────────────────────

class TestBudgetManager:
    def test_initial_budget(self):
        bm = BudgetManager(max_budget=8)
        assert bm.remaining() == 8

    def test_consume_decreases(self):
        bm = BudgetManager(max_budget=8)
        bm.consume(2)
        assert bm.remaining() == 6

    def test_consume_exact_limit(self):
        bm = BudgetManager(max_budget=3)
        bm.consume(3)
        assert bm.remaining() == 0

    def test_consume_over_limit_raises(self):
        bm = BudgetManager(max_budget=3)
        bm.consume(2)
        with pytest.raises(BudgetExhaustedError):
            bm.consume(2)

    def test_reset(self):
        bm = BudgetManager(max_budget=8)
        bm.consume(5)
        bm.reset()
        assert bm.remaining() == 8

    def test_check_can_afford(self):
        bm = BudgetManager(max_budget=3)
        assert bm.can_afford(3) is True
        assert bm.can_afford(4) is False
        bm.consume(2)
        assert bm.can_afford(1) is True
        assert bm.can_afford(2) is False

    def test_usage_report(self):
        bm = BudgetManager(max_budget=8)
        bm.consume(3)
        report = bm.usage_report()
        assert report["max_budget"] == 8
        assert report["consumed"] == 3
        assert report["remaining"] == 5


# ── EvidenceRecorder ─────────────────────────────────────────────

class TestEvidenceRecorder:
    def test_record_source(self, tmp_dir):
        rec = EvidenceRecorder(output_dir=tmp_dir)
        ref = SourceRef(
            tool_name="search_web",
            query="NVDA earnings 2026",
            url="https://example.com/nvda",
            snippet="NVDA reported Q4 revenue...",
            timestamp=None,  # auto-set
        )
        rec.record(ref)
        assert len(rec.sources) == 1

    def test_save_to_jsonl(self, tmp_dir):
        rec = EvidenceRecorder(output_dir=tmp_dir)
        rec.record(SourceRef("search_web", "q1", "http://a.com", "snippet1"))
        rec.record(SourceRef("search_brave", "q2", "http://b.com", "snippet2"))
        filepath = rec.save("test_task")

        assert os.path.exists(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_generate_citations_block(self, tmp_dir):
        rec = EvidenceRecorder(output_dir=tmp_dir)
        rec.record(SourceRef("search_web", "NVDA", "http://a.com", "Revenue up"))
        rec.record(SourceRef("search_brave", "GOOG", "http://b.com", "Earnings beat"))

        md = rec.generate_citations_markdown()
        assert "http://a.com" in md
        assert "http://b.com" in md
        assert "Revenue up" in md

    def test_clear(self, tmp_dir):
        rec = EvidenceRecorder(output_dir=tmp_dir)
        rec.record(SourceRef("x", "q", "u", "s"))
        rec.clear()
        assert len(rec.sources) == 0


# ── ToolBus (integration) ───────────────────────────────────────

class TestToolBus:
    def _make_bus(self, tmp_dir):
        """Create a ToolBus with test tools registered."""
        event_log = EventLog(log_dir=os.path.join(tmp_dir, "events"))
        bus = ToolBus(event_log=event_log, max_budget=8)

        # Register some test tools
        bus.registry.register(ToolDefinition(
            name="search_web",
            category="data",
            handler=lambda query: f"Search results for: {query}",
            permission_level=0,
            budget_cost=1,
            description="Web search",
        ))
        bus.registry.register(ToolDefinition(
            name="fetch_price",
            category="data",
            handler=lambda ticker: {"ticker": ticker, "price": 130.0},
            permission_level=0,
            budget_cost=0,  # free
            description="Fetch stock price",
        ))
        bus.registry.register(ToolDefinition(
            name="place_order",
            category="execution",
            handler=lambda **kwargs: {"status": "staged"},
            permission_level=2,
            budget_cost=0,
            description="Stage an order",
        ))
        return bus

    def test_call_tool_success(self, tmp_dir):
        bus = self._make_bus(tmp_dir)
        ctx = WorkflowContext(workflow_name="test", permission_level=0)
        result = bus.call("fetch_price", {"ticker": "NVDA"}, ctx)
        assert result["ticker"] == "NVDA"
        assert result["price"] == 130.0

    def test_call_deducts_budget(self, tmp_dir):
        bus = self._make_bus(tmp_dir)
        ctx = WorkflowContext(workflow_name="test", permission_level=0)
        bus.call("search_web", {"query": "test"}, ctx)
        assert bus.budget.remaining() == 7

    def test_call_budget_exhaustion(self, tmp_dir):
        bus = ToolBus(event_log=EventLog(log_dir=os.path.join(tmp_dir, "events")), max_budget=2)
        bus.registry.register(ToolDefinition("s", "data", lambda query: "ok", 0, 1, ""))
        ctx = WorkflowContext(workflow_name="test", permission_level=0)
        bus.call("s", {"query": "1"}, ctx)
        bus.call("s", {"query": "2"}, ctx)
        with pytest.raises(BudgetExhaustedError):
            bus.call("s", {"query": "3"}, ctx)

    def test_call_permission_denied(self, tmp_dir):
        bus = self._make_bus(tmp_dir)
        ctx = WorkflowContext(workflow_name="test", permission_level=0)  # read-only
        with pytest.raises(PermissionError):
            bus.call("place_order", {}, ctx)

    def test_call_nonexistent_tool(self, tmp_dir):
        bus = self._make_bus(tmp_dir)
        ctx = WorkflowContext(workflow_name="test", permission_level=0)
        with pytest.raises(KeyError, match="not found"):
            bus.call("nonexistent", {}, ctx)

    def test_call_emits_event(self, tmp_dir):
        bus = self._make_bus(tmp_dir)
        ctx = WorkflowContext(workflow_name="test", permission_level=0)
        bus.call("fetch_price", {"ticker": "GOOG"}, ctx)

        events = bus.event_log.query(event_type="tool.call")
        assert len(events) == 1
        assert events[0].payload["tool_name"] == "fetch_price"

    def test_new_workflow_resets_budget(self, tmp_dir):
        bus = self._make_bus(tmp_dir)
        ctx1 = WorkflowContext(workflow_name="wf1", permission_level=0)
        bus.call("search_web", {"query": "a"}, ctx1)
        assert bus.budget.remaining() == 7

        bus.start_workflow("wf2")
        assert bus.budget.remaining() == 8
