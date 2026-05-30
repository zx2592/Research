"""
DataSource — 数据源抽象基类

All data sources implement this interface.
"""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass
class DataSourceResult:
    """Result returned by any DataSource.fetch()."""
    source_name: str
    data: Dict[str, Any]
    query: str
    version: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "query": self.query,
            "version": self.version,
            "fetched_at": self.fetched_at.isoformat(),
            "data": self.data,
        }


class DataSource(ABC):
    """Abstract base class for all data source adapters."""
    name: str = "base"

    @abstractmethod
    def fetch(self, **kwargs) -> DataSourceResult:
        """Fetch data from the source and return a DataSourceResult."""
        ...
