"""
ToolBus — 统一工具调度总线

Orchestrates tool calls with:
- Permission checking
- Budget enforcement
- Event audit logging
- Evidence recording
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.event_log import Event, EventLog
from core.toolbus.registry import ToolDefinition, ToolRegistry
from core.toolbus.budget import BudgetManager, BudgetExhaustedError
from core.toolbus.evidence import EvidenceRecorder

logger = logging.getLogger(__name__)


@dataclass
class WorkflowContext:
    """Context for the current workflow execution."""
    workflow_name: str
    permission_level: int = 0   # 0=read, 1=write, 2=trade


class ToolBus:
    """
    Unified tool dispatch bus.

    - Registers tools via ToolRegistry
    - Enforces budget via BudgetManager
    - Logs calls to EventLog
    - Records evidence via EvidenceRecorder
    """

    def __init__(
        self,
        event_log: Optional[EventLog] = None,
        max_budget: int = 30,
    ):
        self.registry = ToolRegistry()
        self.budget = BudgetManager(max_budget=max_budget)
        self.evidence = EvidenceRecorder()
        self.event_log = event_log or EventLog()
        self._current_workflow: Optional[str] = None

    def start_workflow(self, workflow_name: str) -> None:
        """Start a new workflow context, resetting budget."""
        self._current_workflow = workflow_name
        self.budget.reset()
        self.evidence.clear()
        self.event_log.emit(Event(
            event_type="workflow.start",
            source="toolbus",
            payload={"workflow": workflow_name},
        ))

    def call(self, tool_name: str, params: Dict[str, Any], context: WorkflowContext) -> Any:
        """
        Call a registered tool.

        Checks:
        1. Tool exists
        2. Permission level is sufficient
        3. Budget allows the call

        Then:
        - Executes the handler
        - Deducts budget
        - Emits audit event
        """
        # 1. Lookup
        tool = self.registry.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool '{tool_name}' not found in registry")

        # 2. Permission check
        if context.permission_level < tool.permission_level:
            raise PermissionError(
                f"Insufficient permission for tool '{tool_name}': "
                f"requires level {tool.permission_level}, "
                f"context has level {context.permission_level}"
            )

        # 3. Budget check & consume
        if tool.budget_cost > 0:
            self.budget.consume(tool.budget_cost)

        # 4. Execute
        try:
            result = tool.handler(**params)
        except Exception as e:
            # Log failure
            self.event_log.emit(Event(
                event_type="tool.call.error",
                source="toolbus",
                payload={
                    "tool_name": tool_name,
                    "params": _safe_serialize(params),
                    "error": str(e),
                    "workflow": context.workflow_name,
                },
            ))
            raise

        # 5. Audit log
        self.event_log.emit(Event(
            event_type="tool.call",
            source="toolbus",
            payload={
                "tool_name": tool_name,
                "params": _safe_serialize(params),
                "workflow": context.workflow_name,
                "budget_remaining": self.budget.remaining(),
            },
        ))

        return result


def _safe_serialize(obj: Any) -> Any:
    """Make params JSON-serializable for audit logging."""
    try:
        import json
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)
