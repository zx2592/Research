"""
opencli DataSource Adapter

Leverages opencli (by jackwener) to transform websites into APIs.
Provides access to 80+ commands across 18+ sites.
"""
import json
import logging
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.datahub.base import DataSource, DataSourceResult

logger = logging.getLogger(__name__)


class OpenCLISource(DataSource):
    """Bridge to opencli for structured web data scraping."""

    name = "opencli"

    def __init__(self, bin_path: str = "opencli"):
        """
        :param bin_path: Path to opencli executable.
        """
        # Windows fix: global npm commands are .cmd files
        if bin_path == "opencli" and shutil.which("opencli.cmd"):
            bin_path = "opencli.cmd"

        self.bin_path = bin_path
        self.available = self._check_dependency()

    def _check_dependency(self) -> bool:
        """Check if opencli is installed."""
        path = shutil.which(self.bin_path)
        if not path:
            logger.warning(
                f"[opencli_src] '{self.bin_path}' not found in PATH. "
                "Please install via 'npm install -g @jackwener/opencli'."
            )
            return False
        return True

    @staticmethod
    def _tokenize(value: Optional[str]) -> List[str]:
        """Split a user-facing command string into CLI tokens."""
        if value is None:
            return []
        text = str(value).strip()
        if not text:
            return []
        return shlex.split(text)

    @classmethod
    def _normalise_site_tokens(cls, site: str, command: Optional[str]) -> tuple[str, List[str]]:
        """Allow adapter-style site/subcommand input while targeting current opencli syntax."""
        site_tokens = cls._tokenize(site)
        command_tokens = cls._tokenize(command)

        if not site_tokens:
            raise ValueError("site is required")

        if len(site_tokens) == 1 and "/" in site_tokens[0] and not command_tokens:
            base_site, subcommand = site_tokens[0].split("/", 1)
            site_tokens = [base_site]
            command_tokens = cls._tokenize(subcommand)

        site_name = site_tokens[0]
        # Add aliases for twitter
        if site_name in {"x", "t"}:
            site_name = "twitter"

        return site_name, site_tokens[1:] + command_tokens

    @staticmethod
    def _coerce_token_values(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if item is not None]
        return [str(value)]

    @classmethod
    def _extract_positional_kwargs(cls, kwargs: Dict[str, Any]) -> List[str]:
        """Map common semantic kwargs to positional opencli arguments."""
        positionals = []
        for key in ("symbol", "ticker", "name", "query", "username", "subreddit", "post_id", "text"):
            if key in kwargs:
                positionals.extend(cls._coerce_token_values(kwargs.pop(key)))
        return positionals

    @classmethod
    def _build_flag_tokens(cls, kwargs: Dict[str, Any]) -> List[str]:
        flags: List[str] = []
        for key, value in kwargs.items():
            if value in (None, False, ""):
                continue
            flag = "-f" if key in {"format", "f"} else f"--{key.replace('_', '-')}"
            if value is True:
                flags.append(flag)
                continue
            for token in cls._coerce_token_values(value):
                flags.extend([flag, token])
        return flags

    @staticmethod
    def _has_format_flag(tokens: List[str]) -> bool:
        return "-f" in tokens or "--format" in tokens

    @staticmethod
    def _split_positionals_and_flags(tokens: List[str]) -> tuple[List[str], List[str]]:
        """Assume opencli positionals come before option flags."""
        positionals: List[str] = []
        flags: List[str] = []
        in_flags = False
        for token in tokens:
            if token.startswith("-"):
                in_flags = True
            if in_flags:
                flags.append(token)
            else:
                positionals.append(token)
        return positionals, flags

    def _fanout_quote(self, site: str, symbols: List[str], flags: List[str]) -> DataSourceResult:
        """Yahoo Finance quote is single-symbol, so fan out multi-symbol requests."""
        aggregated: List[Any] = []
        errors: List[Dict[str, str]] = []

        for symbol in symbols:
            cmd = [self.bin_path, site, "quote", symbol] + flags
            result = self._execute_cmd(cmd, " ".join(cmd))
            if isinstance(result.data, dict) and "error" in result.data:
                errors.append({"symbol": symbol, "error": result.data["error"]})
                continue

            payload = result.data.get("results", [])
            if isinstance(payload, list):
                aggregated.extend(payload)
            elif payload:
                aggregated.append(payload)

        if aggregated:
            data = {
                "results": aggregated,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            if errors:
                data["errors"] = errors
            return DataSourceResult(
                source_name=self.name,
                data=data,
                query=f"{site} quote {' '.join(symbols)}",
            )

        error_text = "; ".join(f"{item['symbol']}: {item['error']}" for item in errors) or "Quote fan-out failed"
        return self._error_result(f"{site} quote {' '.join(symbols)}", error_text)

    def operate(self, action: str, *args, **kwargs) -> DataSourceResult:
        """
        Execute an opencli operate command (browser automation).

        :param action: The action name (e.g., 'open', 'click', 'screenshot', 'eval').
        :param args: Action arguments (e.g., URL for 'open').
        :return: DataSourceResult.
        """
        if not self.available:
            return self._error_result(f"operate {action}", "opencli not available")

        cmd = [self.bin_path, "operate", action]
        for arg in args:
            cmd.append(str(arg))

        # Support optional JSON format for extraction tools like 'eval' or 'get'
        if action in ["eval", "get", "state", "network"]:
            cmd.extend(["-f", "json"])

        query_str = " ".join(cmd)
        return self._execute_cmd(cmd, query_str)

    def doctor(self) -> DataSourceResult:
        """Run opencli doctor to check connectivity."""
        if not self.available:
            return self._error_result("doctor", "opencli not available")

        cmd = [self.bin_path, "doctor"]
        return self._execute_cmd(cmd, "opencli doctor")

    def _execute_cmd(self, cmd: List[str], query_str: str) -> DataSourceResult:
        """Helper to run subprocess and parse output."""
        try:
            logger.info(f"[opencli_src] Executing: {query_str}")
            import platform

            use_shell = platform.system() == "Windows"

            executable = shutil.which(self.bin_path) or self.bin_path
            full_cmd = [executable] + cmd[1:]

            if use_shell:
                quoted_cmd = []
                for part in full_cmd:
                    if " " in part:
                        quoted_cmd.append(f'"{part}"')
                    else:
                        quoted_cmd.append(part)
                final_cmd = " ".join(quoted_cmd)
            else:
                final_cmd = full_cmd

            result = subprocess.run(
                final_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                shell=use_shell,
                timeout=90,  # Browser operations (operate) can be slower
            )

            output = result.stdout.strip()
            parsed_data: Any = []

            if output:
                try:
                    if output.startswith("[") or output.startswith("{"):
                        parsed_data = json.loads(output)
                    else:
                        parsed_data = {"raw": output}
                except json.JSONDecodeError:
                    parsed_data = {"raw": output}

            return DataSourceResult(
                source_name=self.name,
                data={
                    "results": parsed_data,
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

    def fetch(self, site: str, command: Optional[str] = None, *args, **kwargs) -> DataSourceResult:
        """
        Execute an opencli command.
        """
        if not self.available:
            return self._error_result(f"{site} {command}", "opencli not available")

        kwargs = dict(kwargs)
        site_name, command_tokens = self._normalise_site_tokens(site, command)
        command_tokens.extend(str(arg) for arg in args)
        command_tokens.extend(self._extract_positional_kwargs(kwargs))

        if site_name == "yahoo-finance" and command_tokens and command_tokens[0] == "quote":
            quote_symbols, quote_flags = self._split_positionals_and_flags(command_tokens[1:])
            quote_flags.extend(self._build_flag_tokens(kwargs))
            if not self._has_format_flag(quote_flags):
                quote_flags.extend(["-f", "json"])
            if len(quote_symbols) > 1:
                return self._fanout_quote(site_name, quote_symbols, quote_flags)

        cmd = [self.bin_path, site_name] + command_tokens
        cmd.extend(self._build_flag_tokens(kwargs))
        if not self._has_format_flag(cmd):
            cmd.extend(["-f", "json"])

        query_str = " ".join(cmd)
        return self._execute_cmd(cmd, query_str)

    def _error_result(self, query: str, message: str) -> DataSourceResult:
        logger.error(f"[opencli_src] {message}")
        return DataSourceResult(
            source_name=self.name,
            data={"error": message, "results": []},
            query=query,
        )
