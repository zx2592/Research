"""
ToolRegistry — 统一工具注册表

Maintains a registry of all available tools (data, research, execution, etc.)
and supports lookup by name or category.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolDefinition:
    """Defines a single tool in the system."""
    name: str                   # e.g. "search_web", "fetch_price"
    category: str               # "data" / "research" / "execution" / "knowledge"
    handler: Callable           # The actual function to execute
    permission_level: int       # 0=read, 1=write, 2=trade
    budget_cost: int            # Budget points consumed per call
    description: str            # Human-readable description


class ToolRegistry:
    """Manages registration and lookup of tools."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool. Raises ValueError if name already exists."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name, or None if not found."""
        return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> List[str]:
        """List tool names, optionally filtered by category."""
        if category:
            return [t.name for t in self._tools.values() if t.category == category]
        return list(self._tools.keys())
