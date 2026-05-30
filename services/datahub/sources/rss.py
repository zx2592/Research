"""
RSS DataSource Adapter

Parses RSS/Atom feeds for news aggregation.
No API key required.
"""
import logging
import urllib.request
from datetime import datetime, timezone
from typing import List, Optional
import xml.etree.ElementTree as ET

from services.datahub.base import DataSource, DataSourceResult

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = {
    "reuters": "https://feeds.reuters.com/reuters/businessNews",
    "ft":      "https://www.ft.com/rss/home/uk",
    "wsj":     "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
}


class RSSSource(DataSource):
    """Fetch and parse RSS/Atom news feeds."""
    name = "rss"

    def __init__(self, feeds: Optional[dict] = None):
        self.feeds = feeds or DEFAULT_FEEDS

    def fetch(self, feed_name: str = "reuters", max_items: int = 20, **kwargs) -> DataSourceResult:
        url = self.feeds.get(feed_name, feed_name)  # allow raw URLs too
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AlphaSystem/3.0 RSS Reader"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read()
            items = _parse_feed(content, max_items)
            return DataSourceResult(
                source_name=self.name,
                data={
                    "feed": feed_name,
                    "url": url,
                    "items": items,
                    "count": len(items),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                },
                query=feed_name,
            )
        except Exception as e:
            logger.error(f"[rss_src] Error fetching {feed_name}: {e}")
            return DataSourceResult(
                source_name=self.name,
                data={"feed": feed_name, "error": str(e), "items": []},
                query=feed_name,
            )


def _parse_feed(content: bytes, max_items: int) -> List[dict]:
    """Parse RSS/Atom XML and extract items."""
    try:
        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = []

        # RSS 2.0
        for item in root.findall(".//item")[:max_items]:
            items.append({
                "title": _text(item, "title"),
                "link": _text(item, "link"),
                "description": (_text(item, "description") or "")[:300],
                "pub_date": _text(item, "pubDate"),
            })

        # Atom
        if not items:
            for entry in root.findall(".//atom:entry", ns)[:max_items]:
                items.append({
                    "title": _text(entry, "atom:title", ns),
                    "link": entry.find("atom:link", ns).get("href", "") if entry.find("atom:link", ns) is not None else "",
                    "description": (_text(entry, "atom:summary", ns) or "")[:300],
                    "pub_date": _text(entry, "atom:updated", ns),
                })

        return items
    except Exception as e:
        logger.warning(f"[rss_src] XML parse error: {e}")
        return []


def _text(el, tag: str, ns: dict = None) -> Optional[str]:
    child = el.find(tag, ns) if ns else el.find(tag)
    return child.text.strip() if child is not None and child.text else None
