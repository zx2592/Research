"""
ReportMetadata + MetadataStore — 报告元数据管理

Adds structured metadata to every research report so they can
be searched, filtered, and linked to other artifacts.

Stored as append-only JSONL (one line per report).
"""
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ReportMetadata:
    """Metadata for a single research report."""
    report_id: str
    ticker: str
    report_type: str            # "deep" / "quick" / "value" / "scan" etc.
    title: str
    conclusion: str
    confidence: float
    tags: List[str]
    source_file: str            # Relative path to the .md file
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    linked_audit_id: Optional[str] = None   # Links to a DecisionAudit if applicable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "ticker": self.ticker,
            "report_type": self.report_type,
            "title": self.title,
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "tags": self.tags,
            "source_file": self.source_file,
            "created_at": self.created_at.isoformat(),
            "linked_audit_id": self.linked_audit_id,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReportMetadata":
        ts = d.get("created_at")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            report_id=d["report_id"],
            ticker=d["ticker"],
            report_type=d["report_type"],
            title=d["title"],
            conclusion=d["conclusion"],
            confidence=float(d["confidence"]),
            tags=d.get("tags", []),
            source_file=d["source_file"],
            created_at=ts or datetime.now(timezone.utc),
            linked_audit_id=d.get("linked_audit_id"),
        )


class MetadataStore:
    """
    Append-only JSONL store for report metadata.

    - save(): add a metadata record
    - load_all(): read all records
    - find_by_ticker(): filter by ticker
    - find_by_tag(): filter by tag
    """

    def __init__(self, store_path: str = "data/knowledge/metadata.jsonl"):
        self.store_path = store_path
        os.makedirs(os.path.dirname(store_path), exist_ok=True)

    def save(self, metadata: ReportMetadata) -> None:
        """Append a metadata record to the store."""
        with open(self.store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(metadata.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> List[ReportMetadata]:
        """Load all metadata records."""
        if not os.path.exists(self.store_path):
            return []
        records = []
        with open(self.store_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(ReportMetadata.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, KeyError):
                        pass
        return records

    def find_by_ticker(self, ticker: str) -> List[ReportMetadata]:
        """Find all reports for a given ticker."""
        return [m for m in self.load_all() if m.ticker == ticker]

    def find_by_tag(self, tag: str) -> List[ReportMetadata]:
        """Find all reports with a given tag."""
        return [m for m in self.load_all() if tag in m.tags]
