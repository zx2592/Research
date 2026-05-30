"""
DataCache — 文件缓存 (TTL-based)

File-based cache with configurable TTL (seconds).
Cache key = {source_name}::{query_key}
Storage: JSON files in cache_dir/
Uses atomic writes (tempfile + os.replace) for concurrency safety.
"""
import hashlib
import json
import logging
import os
import tempfile
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DataCache:
    """File-based cache with TTL."""

    def __init__(self, cache_dir: str = "data/cache", default_ttl: int = 3600):
        """
        Args:
            cache_dir: Directory to store cache files
            default_ttl: Default time-to-live in seconds (0 = never cache)
        """
        self.cache_dir = cache_dir
        self.default_ttl = default_ttl
        os.makedirs(cache_dir, exist_ok=True)

    def _key_to_path(self, source: str, query: str) -> str:
        key = f"{source}::{query}"
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{h}.json")

    def get(self, source: str, query: str, ttl: Optional[int] = None) -> Optional[Any]:
        """Return cached data or None if missing/expired/corrupt."""
        path = self._key_to_path(source, query)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("缓存文件损坏，已删除: %s — %s", path, exc)
            try:
                os.remove(path)
            except OSError:
                pass
            return None
        effective_ttl = ttl if ttl is not None else self.default_ttl
        if effective_ttl == 0:
            return None  # TTL=0 means never return cached
        age = time.time() - record.get("cached_at", 0)
        if age > effective_ttl:
            return None
        return record.get("data")

    def set(self, source: str, query: str, data: Any) -> None:
        """Store data in the cache atomically."""
        path = self._key_to_path(source, query)
        record = {"cached_at": time.time(), "source": source, "query": query, "data": data}
        fd, tmp_path = tempfile.mkstemp(dir=self.cache_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def invalidate(self, source: str, query: str) -> None:
        """Remove a cached entry."""
        path = self._key_to_path(source, query)
        if os.path.exists(path):
            os.remove(path)
