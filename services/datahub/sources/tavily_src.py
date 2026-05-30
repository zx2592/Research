"""
Tavily DataSource Adapter

Wraps Tavily Search API for AI-optimized web search.
Requires TAVILY_API_KEY in environment.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from services.datahub.base import DataSource, DataSourceResult

logger = logging.getLogger(__name__)


class TavilySource(DataSource):
    """AI-optimized web search via Tavily API."""
    name = "tavily"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY", "")

    def fetch(self, query: str, max_results: int = 5, **kwargs) -> DataSourceResult:
        if not self.api_key:
            return DataSourceResult(
                source_name=self.name,
                data={"error": "TAVILY_API_KEY not set", "results": []},
                query=query,
            )
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=self.api_key)
            response = client.search(query=query, max_results=max_results)
            results = [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "content": r.get("content", "")[:500],
                    "score": r.get("score"),
                }
                for r in response.get("results", [])
            ]
            return DataSourceResult(
                source_name=self.name,
                data={
                    "query": query,
                    "results": results,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                },
                query=query,
            )
        except Exception as e:
            logger.error(f"[tavily_src] Error: {e}")
            return DataSourceResult(
                source_name=self.name,
                data={"error": str(e), "results": []},
                query=query,
            )
