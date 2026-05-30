"""
EvidenceRecorder — 引用链记录器

Records every data source / search result used during a workflow,
enabling audit trails and citation blocks in Markdown reports.
"""
import os
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class SourceRef:
    """A single source reference / citation."""
    tool_name: str          # Which tool produced this
    query: str              # The query or request
    url: str                # Source URL
    snippet: str            # Key excerpt
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "query": self.query,
            "url": self.url,
            "snippet": self.snippet,
            "timestamp": self.timestamp.isoformat(),
        }


class EvidenceRecorder:
    """Records and persists source citations for a workflow."""

    def __init__(self, output_dir: str = "data/evidence"):
        self.output_dir = output_dir
        self.sources: List[SourceRef] = []

    def record(self, ref: SourceRef) -> None:
        """Record a source reference."""
        self.sources.append(ref)

    def save(self, task_name: str) -> str:
        """
        Save all recorded sources to a JSONL file.
        Returns the file path.
        """
        os.makedirs(self.output_dir, exist_ok=True)
        filename = f"{task_name}_sources.jsonl"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            for ref in self.sources:
                f.write(json.dumps(ref.to_dict(), ensure_ascii=False) + "\n")
        return filepath

    def generate_citations_markdown(self) -> str:
        """Generate a Markdown citations block from recorded sources."""
        if not self.sources:
            return ""
        lines = ["## 引用来源 (Sources)\n"]
        for i, ref in enumerate(self.sources, 1):
            lines.append(f"{i}. **[{ref.tool_name}]** {ref.query}")
            lines.append(f"   - URL: {ref.url}")
            lines.append(f"   - {ref.snippet}")
            lines.append("")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all recorded sources."""
        self.sources.clear()
