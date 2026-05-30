"""
bb-browser ToolBus Tools — 浏览器 API 工具总线适配器

Provides AI agents dengan direct access to web data via local browser login state.
"""
import logging
from typing import Any, Dict, Optional, List

from core.toolbus.registry import ToolDefinition, ToolRegistry
from services.datahub.sources.bb_browser_src import BBBrowserSource

logger = logging.getLogger(__name__)

class BBBrowserTool:
    """ToolBus-compatible wrapper for BBBrowserSource."""

    def __init__(self, bin_path: str = "bb-browser"):
        self.source = BBBrowserSource(bin_path=bin_path)

    def call(self, site: str, args: Optional[List[Any]] = None, jq: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Execute a bb-browser site command.
        
        :param site: The site/adapter name (e.g., 'xueqiu/hot-stock').
        :param args: Positional arguments for the adapter.
        :param jq: Optional JQ filter.
        :return: Result dict with 'results' key.
        """
        args = args or []
        result = self.source.fetch(site, *args, jq=jq, **kwargs)
        return result.data

def register_bb_browser_tools(
    registry: ToolRegistry,
    bin_path: str = "bb-browser",
    budget_cost: int = 1,
) -> None:
    """
    Register bb-browser tools into a ToolRegistry.
    """
    tool = BBBrowserTool(bin_path=bin_path)

    registry.register(ToolDefinition(
        name="browser.site_fetch",
        category="data",
        handler=tool.call,
        permission_level=0,
        budget_cost=budget_cost,
        description="Fetch structured data from websites using local browser login state (bb-browser).",
    ))
