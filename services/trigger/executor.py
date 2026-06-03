from __future__ import annotations

from typing import Any, Protocol

from .models import WorkflowInvocation


class WorkflowExecutor(Protocol):
    """Executor interface so trigger core stays environment-agnostic."""

    def invoke(self, invocation: WorkflowInvocation) -> Any:
        ...


class ResearchWorkflowExecutor:
    """Default executor backed by ResearchAgent (API-driven)."""

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


def build_workflow_executor() -> WorkflowExecutor:
    """Build the API-driven workflow executor.

    Triggered workflows always run directly via ResearchAgent (Gemini API).
    """
    return ResearchWorkflowExecutor(
        agent_factory=lambda: __import__("research_cli").ResearchAgent()
    )
