"""
KnowledgeIndex — 全文搜索索引

Indexes all .md files in the reports directory for full-text search.
Uses pure-Python in-memory index (no external dependencies).
"""
import os
import re
from typing import Any, Dict, List


class KnowledgeIndex:
    """
    Lightweight full-text index over Markdown report files.

    Builds an in-memory inverted index on first build().
    Supports keyword search with snippet extraction.
    """

    def __init__(self, reports_dir: str):
        self.reports_dir = reports_dir
        # Map: word → set of filenames containing it
        self._index: Dict[str, set] = {}
        # Map: filename → full content
        self._content: Dict[str, str] = {}

    def build(self) -> None:
        """Scan all .md files in reports_dir and build the index."""
        self._index.clear()
        self._content.clear()

        if not os.path.exists(self.reports_dir):
            return

        for fname in os.listdir(self.reports_dir):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(self.reports_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                self._content[fname] = content
                for word in _tokenize(content):
                    self._index.setdefault(word, set()).add(fname)
            except OSError:
                pass

    def count(self) -> int:
        """Number of indexed files."""
        return len(self._content)

    def list_files(self) -> List[str]:
        """Return all indexed file names."""
        return list(self._content.keys())

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for a keyword or phrase.

        Returns list of dicts: {file, snippet, score}
        Score = number of matching query words found in file.
        """
        if not self._index:
            return []

        query_words = _tokenize(query)
        if not query_words:
            return []

        # Score each file by how many query words appear in it
        scores: Dict[str, int] = {}
        for word in query_words:
            for fname in self._index.get(word, set()):
                scores[fname] = scores.get(fname, 0) + 1

        if not scores:
            return []

        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max_results]

        results = []
        for fname, score in ranked:
            content = self._content.get(fname, "")
            snippet = _extract_snippet(content, query_words)
            results.append({
                "file": fname,
                "score": score,
                "snippet": snippet,
            })
        return results


def _tokenize(text: str) -> List[str]:
    """Lowercase, strip punctuation, tokenize."""
    text = text.lower()
    words = re.findall(r"[a-z0-9\u4e00-\u9fff]+", text)
    return [w for w in words if len(w) > 1]


def _extract_snippet(content: str, query_words: List[str], window: int = 120) -> str:
    """Extract a ~window-char snippet around the first query word match."""
    content_lower = content.lower()
    for word in query_words:
        idx = content_lower.find(word)
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(content), idx + window)
            return content[start:end].replace("\n", " ").strip()
    return content[:window].strip()
