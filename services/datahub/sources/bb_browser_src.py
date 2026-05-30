"""
bb-browser (BadBoy Browser) DataSource Adapter

Leverages a real browser's login state via the bb-browser CLI/MCP.
Provides access to sites like Xueqiu, Eastmoney, Twitter, etc., without formal APIs.

Usage:
    bb_source = BBBrowserSource()
    res = bb_source.fetch(site="xueqiu/hot-stock", count=5)
"""
import logging
import subprocess
import json
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.datahub.base import DataSource, DataSourceResult

logger = logging.getLogger(__name__)

class BBBrowserSource(DataSource):
    """Bridge to bb-browser CLI for authenticated web data scraping."""
    name = "bb-browser"

    def __init__(self, bin_path: str = "bb-browser"):
        """
        :param bin_path: Path to bb-browser executable. Assumes it's in PATH by default.
        """
        self.bin_path = bin_path
        self.available = self._check_dependency()

    def _check_dependency(self) -> bool:
        """Check if bb-browser is installed in the system."""
        path = shutil.which(self.bin_path)
        if not path:
            logger.warning(f"[bb_browser_src] '{self.bin_path}' not found in PATH. "
                           "Please install via 'npm install -g bb-browser'.")
            return False
        return True

    def fetch(self, site: str, *args, **kwargs) -> DataSourceResult:
        """
        Execute a bb-browser site command.
        
        :param site: The site/command string (e.g., 'xueqiu/hot-stock', 'eastmoney/stock').
        :param count: Optional argument passed to many adapters.
        :param jq: JSON query filter.
        :return: DataSourceResult containing the raw or filtered JSON output.
        """
        query_str = f"site {site} {' '.join(map(str, args))}"

        if not self.available:
            return self._error_result(query_str, f"bb-browser not available (binary '{self.bin_path}' not found). Fallback to standard search recommended.")
        
        # Prepare CLI arguments
        cmd = [self.bin_path, "site", site]
        for arg in args:
            cmd.append(str(arg))
        
        # Always request JSON for structured parsing
        cmd.append("--json")
        
        # Optional JQ filtering inside bb-browser
        jq_expr = kwargs.get("jq")
        if jq_expr:
            cmd.extend(["--jq", jq_expr])

        try:
            logger.info(f"[bb_browser_src] Executing: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                timeout=30 # Browser operations might be slow
            )
            
            # Parse output. bb-browser usually returns line-delimited JSON for multiple items.
            output = result.stdout.strip()
            parsed_data = []
            
            if output:
                # Attempt to parse as full JSON or line-by-line JSON (Ndjson)
                try:
                    parsed_data = json.loads(output)
                except json.JSONDecodeError:
                    # Fallback for line-delimited JSON
                    for line in output.splitlines():
                        if line.strip():
                            try:
                                parsed_data.append(json.loads(line))
                            except (json.JSONDecodeError, ValueError):
                                parsed_data.append(line)

            return DataSourceResult(
                source_name=self.name,
                data={
                    "site": site,
                    "results": parsed_data,
                    "raw_output": output if not parsed_data else None,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                },
                query=query_str,
            )

        except subprocess.TimeoutExpired:
            return self._error_result(query_str, "Command timed out")
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr or str(e)
            return self._error_result(query_str, f"Exit code {e.returncode}: {err_msg}")
        except Exception as e:
            return self._error_result(query_str, str(e))

    def _error_result(self, query: str, message: str) -> DataSourceResult:
        logger.error(f"[bb_browser_src] {message}")
        return DataSourceResult(
            source_name=self.name,
            data={"error": message, "results": []},
            query=query,
        )
