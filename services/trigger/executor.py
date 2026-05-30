from __future__ import annotations

import os
from typing import Any, Protocol

from .inbox import TriggerInboxService
from .models import WorkflowInvocation


class WorkflowExecutor(Protocol):
    """Executor interface so trigger core stays environment-agnostic."""

    def invoke(self, invocation: WorkflowInvocation) -> Any:
        ...


class ResearchWorkflowExecutor:
    """Default executor backed by ResearchAgent."""

    def __init__(self, agent_factory=None):
        self._agent_factory = agent_factory
        self._agent = None

    def _get_agent(self):
        if self._agent is None:
            factory = self._agent_factory
            if factory is None:
                from research_cli import ResearchAgent

                factory = ResearchAgent
            self._agent = factory()
        return self._agent

    def invoke(self, invocation: WorkflowInvocation) -> Any:
        agent = self._get_agent()
        return agent.run_workflow(
            invocation.workflow,
            invocation.reason,
            ticker=invocation.ticker,
        )


class DesktopQueueWorkflowExecutor:
    """Desktop-safe executor that queues invocations for manual handling."""

    def __init__(self, queue_path: str = "data/trigger/desktop_queue.jsonl", inbox_service: TriggerInboxService | None = None):
        self.queue_path = queue_path
        self.inbox_service = inbox_service or TriggerInboxService(queue_path=queue_path)

    def invoke(self, invocation: WorkflowInvocation) -> Any:
        item = self.inbox_service.enqueue(invocation)
        return {
            "status": "queued",
            "queue_path": self.queue_path,
            "workflow": invocation.workflow,
            "item_id": item["item_id"],
        }


def build_workflow_executor(mode: str = "auto") -> WorkflowExecutor:
    """Build an executor for the requested environment mode."""
    resolved_mode = mode
    if resolved_mode == "auto":
        resolved_mode = os.getenv("TRIGGER_EXECUTOR_MODE", "").strip().lower()
    if not resolved_mode or resolved_mode == "auto":
        llm_mode = os.getenv("LLM_MODE", "").strip().lower()
        if llm_mode in ("desktop", "vps"):
            resolved_mode = llm_mode
        else:
            # "auto" or unset: default to desktop on Windows, vps otherwise
            resolved_mode = "desktop" if os.name == "nt" else "vps"
    if resolved_mode == "desktop":
        return DesktopQueueWorkflowExecutor()
    if resolved_mode != "vps":
        raise ValueError(f"Unsupported trigger executor mode: {resolved_mode}")
    return ResearchWorkflowExecutor(agent_factory=lambda: __import__("research_cli").ResearchAgent(llm_mode="vps"))
