"""
DataHub — 统一数据访问层

Central registry and dispatcher for all data sources.
Supports caching, versioning, and cache bypass.
"""
import logging
from typing import Any, Dict, List, Optional

from services.datahub.base import DataSource, DataSourceResult
from services.datahub.cache import DataCache

logger = logging.getLogger(__name__)


class DataHub:
    """
    Unified data access layer.

    - register(): add a DataSource adapter
    - fetch(): get data from a named source (with caching)
    - list_sources(): enumerate registered sources
    """

    def __init__(self, cache: Optional[DataCache] = None):
        self._sources: Dict[str, DataSource] = {}
        self.cache = cache or DataCache()

    def register(self, source: DataSource) -> None:
        """Register a data source adapter."""
        self._sources[source.name] = source
        logger.info(f"DataHub: registered source '{source.name}'")

    def list_sources(self) -> List[str]:
        """Return names of all registered sources."""
        return list(self._sources.keys())

    def fetch(
        self,
        source_name: str,
        bypass_cache: bool = False,
        ttl: Optional[int] = None,
        **kwargs,
    ) -> DataSourceResult:
        """Fetch data from a registered source."""
        source = self._sources.get(source_name)
        if source is None:
            raise KeyError(f"DataSource '{source_name}' not registered")

        cache_key = str(sorted(kwargs.items()))
        if not bypass_cache:
            cached = self.cache.get(source_name, cache_key, ttl=ttl)
            if cached is not None:
                return DataSourceResult(source_name=source_name, data=cached, query=cache_key)

        result = source.fetch(**kwargs)
        if isinstance(result.data, dict) and "error" in result.data:
            return result

        self.cache.set(source_name, cache_key, result.data)
        return result

    def operate(self, source_name: str, action: str, *args, **kwargs) -> DataSourceResult:
        """Execute a browser automation operation on a source."""
        source = self._sources.get(source_name)
        if source is None:
            raise KeyError(f"DataSource '{source_name}' not registered")
        
        if hasattr(source, "operate"):
            return source.operate(action, *args, **kwargs)
        raise NotImplementedError(f"Source '{source_name}' does not support 'operate'")

    def doctor(self, source_name: str) -> DataSourceResult:
        """Run connectivity check on a source."""
        source = self._sources.get(source_name)
        if source is None:
            raise KeyError(f"DataSource '{source_name}' not registered")
        
        if hasattr(source, "doctor"):
            return source.doctor()
        raise NotImplementedError(f"Source '{source_name}' does not support 'doctor'")
