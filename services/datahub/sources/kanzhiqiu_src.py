"""
kanzhiqiu DataSource Adapter

Provides access to kanzhiqiu.com research report data via cached browser-fetched JSON.
Data is fetched in two steps:
  1. Browser fetch (via Claude MCP) saves JSON to data/kanzhiqiu/.cache/
  2. This adapter reads the cache and returns structured data.
"""
import logging
from datetime import date, timezone, datetime
from typing import Optional

from services.datahub.base import DataSource, DataSourceResult

logger = logging.getLogger(__name__)


class KanzhiqiuSource(DataSource):
    """DataHub adapter for kanzhiqiu.com research reports."""
    name = "kanzhiqiu"

    def fetch(self, command: str = "digest", **kwargs) -> DataSourceResult:
        """
        Fetch kanzhiqiu data from local cache.

        :param command: What to fetch:
            - "digest"     → Full structured context (morning + topics + news)
            - "hot_topics" → Hot research topics only
            - "news"       → News focus / recommendations only
            - "morning"    → Morning meeting reports only
            - "raw"        → Raw cached JSON
        :return: DataSourceResult
        """
        from integrations.kanzhiqiu.digest import (
            load_cached_data, build_context, enrich_morning_content
        )

        query_str = f"kanzhiqiu {command}"
        data = load_cached_data()

        if not data:
            return self._error_result(query_str, "No cached data for today. Run browser fetch first.")

        if command == "raw":
            return DataSourceResult(
                source_name=self.name,
                data=data,
                query=query_str,
            )

        if command == "digest":
            enrich_morning_content(data)
            context = build_context(data)
            return DataSourceResult(
                source_name=self.name,
                data={
                    "context": context,
                    "stats": {
                        "morning_reports": len(data.get("morningReports", [])),
                        "hot_topics": len(data.get("hotTopics", [])),
                        "viewpoints": len(data.get("viewpoints", [])),
                        "news": len(data.get("news", [])),
                    },
                    "date": data.get("date", ""),
                    "fetched_at": data.get("fetchedAt", ""),
                },
                query=query_str,
            )

        if command == "hot_topics":
            topics = data.get("hotTopics", [])
            return DataSourceResult(
                source_name=self.name,
                data={"hot_topics": topics, "count": len(topics)},
                query=query_str,
            )

        if command == "news":
            news = data.get("news", [])
            return DataSourceResult(
                source_name=self.name,
                data={"news": news, "count": len(news)},
                query=query_str,
            )

        if command == "morning":
            enrich_morning_content(data)
            reports = data.get("morningReports", [])
            return DataSourceResult(
                source_name=self.name,
                data={"morning_reports": reports, "count": len(reports)},
                query=query_str,
            )

        return self._error_result(query_str, f"Unknown command: {command}")

    def _error_result(self, query: str, message: str) -> DataSourceResult:
        logger.warning(f"[kanzhiqiu_src] {message}")
        return DataSourceResult(
            source_name=self.name,
            data={"error": message},
            query=query,
        )
