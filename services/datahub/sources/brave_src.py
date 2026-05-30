"""
Brave Search DataSource Adapter

Wraps Brave Search API for privacy-preserving web search.
Requires BRAVE_SEARCH_API_KEY in environment.
"""
import logging
import os
import urllib.request
import json
from datetime import datetime, timezone
from typing import Optional

from services.datahub.base import DataSource, DataSourceResult

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSource(DataSource):
    """Web search via Brave Search API."""
    name = "brave"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("BRAVE_SEARCH_API_KEY", "")

    def fetch(self, query: str, count: int = 5, **kwargs) -> DataSourceResult:
        if not self.api_key:
            return DataSourceResult(
                source_name=self.name,
                data={"error": "BRAVE_SEARCH_API_KEY not set", "results": []},
                query=query,
            )
        try:
            params = urllib.parse.urlencode({"q": query, "count": count})
            url = f"{BRAVE_SEARCH_URL}?{params}"
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": self.api_key,
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            web_results = data.get("web", {}).get("results", [])
            results = [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "description": r.get("description", "")[:400],
                }
                for r in web_results
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
            logger.error(f"[brave_src] Error: {e}")
            return DataSourceResult(
                source_name=self.name,
                data={"error": str(e), "results": []},
                query=query,
            )


# Fix: import urllib.parse
import urllib.parse
