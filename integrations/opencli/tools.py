"""
opencli ToolBus Tools — 适配器工具总线
"""
import logging
from typing import Any, Dict, Optional, List

from core.toolbus.registry import ToolDefinition, ToolRegistry
from services.datahub.sources.opencli_src import OpenCLISource

logger = logging.getLogger(__name__)

class OpenCLITool:
    """ToolBus-compatible wrapper for OpenCLISource."""

    def __init__(self, bin_path: str = "opencli"):
        self.source = OpenCLISource(bin_path=bin_path)

    def call(self, site: str, command: Optional[str] = None, args: Optional[List[Any]] = None, **kwargs) -> Dict[str, Any]:
        """
        Execute an opencli command.
        
        :param site: The site name (e.g., 'xueqiu').
        :param command: The sub-command (e.g., 'hot').
        :param args: Additional positional arguments.
        :return: Result dict with 'results' key.
        """
        args = args or []
        result = self.source.fetch(site, command, *args, **kwargs)
        return result.data

def register_opencli_tools(
    registry: ToolRegistry,
    bin_path: str = "opencli",
    budget_cost: int = 1,
) -> None:
    """
    Register opencli tools into a ToolRegistry.
    """
    tool = OpenCLITool(bin_path=bin_path)

    registry.register(ToolDefinition(
        name="browser.opencli_fetch",
        category="data",
        handler=tool.call,
        permission_level=0,
        budget_cost=budget_cost,
        description="Fetch high-quality structured data from 80+ commands (xueqiu, bilibili, twitter, etc) using opencli.",
    ))
