"""
BudgetManager — 工具调用预算控制

Enforces per-workflow search/tool call limits.
Default: 8 search calls per workflow task.
"""


class BudgetExhaustedError(Exception):
    """Raised when a tool call would exceed the budget."""
    pass


class BudgetManager:
    """Tracks and enforces budget for tool calls within a workflow."""

    def __init__(self, max_budget: int = None):
        from core import settings
        self.max_budget = max_budget if max_budget is not None else settings.search.budget_max
        self._consumed = 0

    def remaining(self) -> int:
        """How many budget points are left."""
        return self.max_budget - self._consumed

    def can_afford(self, cost: int) -> bool:
        """Check if a call with the given cost is within budget."""
        return self._consumed + cost <= self.max_budget

    def consume(self, cost: int) -> None:
        """
        Consume budget points. Raises BudgetExhaustedError if over limit.
        """
        if not self.can_afford(cost):
            raise BudgetExhaustedError(
                f"Budget exhausted: {self._consumed}/{self.max_budget} used, "
                f"cannot afford {cost} more"
            )
        self._consumed += cost

    def reset(self) -> None:
        """Reset consumed budget to zero (for a new workflow)."""
        self._consumed = 0

    def usage_report(self) -> dict:
        """Return a dict summarizing budget usage."""
        return {
            "max_budget": self.max_budget,
            "consumed": self._consumed,
            "remaining": self.remaining(),
        }
