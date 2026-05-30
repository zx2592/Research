#!/usr/bin/env python3
"""
IDE Provider abstraction for desktop mode LLM execution.

Supports three IDE environments:
  - ClaudeCodeProvider  → subprocess calls to `claude` CLI
  - CodexProvider       → subprocess calls to `codex` CLI
  - GeminiADCProvider   → google-genai SDK with Application Default Credentials

Each provider can execute tool-calling workflows via a text-based protocol
(subprocess providers) or native function calling (Gemini ADC).
"""

import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool description builder
# ---------------------------------------------------------------------------

def build_tool_descriptions(tools):
    """Convert a list of Python callables into human-readable text descriptions.

    Used by subprocess-based providers (Claude Code, Codex) to describe
    available tools in the system prompt.
    """
    if not tools:
        return ""
    lines = []
    for func in tools:
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""
        lines.append(f"### {func.__name__}{sig}")
        if doc:
            lines.append(doc)
        lines.append("")
    return "\n".join(lines)


TOOL_CALL_PROTOCOL = """
## MANDATORY Tool Calling Protocol

**你必须通过 <tool_call> 块来调用工具。这是唯一的工具调用方式。**
**不要自己编造数据。需要实时信息时，必须先调用 search_web。**
**完成所有研究后，必须调用 write_to_file 保存报告。**

### 格式

需要调用工具时，输出：

<tool_call>
{"name": "函数名", "arguments": {"参数名": "参数值"}}
</tool_call>

可同时输出多个 <tool_call> 块。输出 <tool_call> 后**立即停止**，不要写其他内容，等待我返回结果。

我会返回：

<tool_result name="函数名" status="ok">
...结果...
</tool_result>

收到结果后，继续分析或调用更多工具。当你拥有足够信息后，直接输出最终回答（不再包含 <tool_call>）。

### 示例

用户任务: 研究 AAPL 最新动态

正确的第一步输出:

<tool_call>
{"name": "search_web", "arguments": {"query": "AAPL Apple latest news 2026"}}
</tool_call>

（等待结果后继续研究，最后调用 write_to_file 保存报告）
""".strip()

# ---------------------------------------------------------------------------
# Subprocess tool-call loop
# ---------------------------------------------------------------------------

TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def _git_bash_is_usable(path):
    """Return True when the Git Bash launcher exists and can start cleanly."""
    if not path or not os.path.isfile(path):
        return False
    try:
        kwargs = dict(
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="replace",
        )
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run([path, "--version"], **kwargs)
        return result.returncode == 0
    except Exception:
        return False


def _resolve_git_bash(which_result):
    """Given a bash path (possibly Git\\usr\\bin\\bash.exe), return Git\\bin\\bash.exe.

    Claude Code requires the Git\\bin\\bash.exe launcher, not the raw
    usr\\bin\\bash.exe binary.
    """
    if not which_result:
        return None
    normalised = which_result.replace("/", os.sep)
    # If the path is Git\usr\bin\bash.exe, derive Git\bin\bash.exe
    usr_bin_marker = os.sep + "usr" + os.sep + "bin" + os.sep
    if usr_bin_marker in normalised.lower():
        idx = normalised.lower().index(usr_bin_marker)
        git_root = normalised[:idx]
        launcher = os.path.join(git_root, "bin", "bash.exe")
        if os.path.isfile(launcher):
            return launcher
    # Already a Git\bin\bash.exe path
    if "Git" in normalised and os.path.isfile(normalised):
        return normalised
    return None


def _build_subprocess_env():
    """Build environment dict for subprocess calls on Windows.

    Auto-detects git-bash location for Claude Code if not already set.
    Claude Code requires Git\\bin\\bash.exe (the launcher), not Git\\usr\\bin\\bash.exe.
    """
    env = os.environ.copy()
    if sys.platform == "win32" and not env.get("CLAUDE_CODE_GIT_BASH_PATH"):
        # 1) Try deriving from shutil.which("bash")
        resolved = _resolve_git_bash(shutil.which("bash"))
        if resolved:
            env["CLAUDE_CODE_GIT_BASH_PATH"] = resolved
            logger.debug("Auto-detected git-bash: %s", resolved)
            return env

        # 2) Try common hardcoded locations
        for candidate in [
            r"C:\Program Files\Git\bin\bash.exe",
            r"D:\software\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]:
            if os.path.isfile(candidate):
                env["CLAUDE_CODE_GIT_BASH_PATH"] = candidate
                logger.debug("Auto-detected git-bash: %s", candidate)
                break
    return env


class SubprocessToolLoop:
    """Execute a multi-turn tool-calling loop through a CLI subprocess."""

    MAX_ITERATIONS = None  # set in __init__ from settings

    def __init__(self, cli_cmd, tool_map, timeout=600, env=None, prompt_via="stdin"):
        from core import settings
        self.cli_cmd = cli_cmd
        self.tool_map = tool_map
        self.timeout = timeout
        self.env = env
        self.prompt_via = prompt_via  # "stdin" or "arg"
        if self.MAX_ITERATIONS is None:
            self.MAX_ITERATIONS = settings.tool_loop.max_iterations

    def run(self, initial_prompt):
        """Run the tool loop starting with *initial_prompt*.

        Returns the final text output (the response without tool_call blocks).
        """
        prompt = initial_prompt
        last_output = ""

        for iteration in range(self.MAX_ITERATIONS):
            output = self._call_cli(prompt)
            last_output = output
            calls = TOOL_CALL_RE.findall(output)

            if not calls:
                return self._strip_tool_calls(output)

            results = []
            for call_json in calls:
                try:
                    parsed = json.loads(call_json)
                    name = parsed["name"]
                    arguments = parsed.get("arguments", {})
                    func = self.tool_map.get(name)
                    if func is None:
                        result_text = f"Error: unknown tool '{name}'"
                        status = "error"
                    else:
                        result_text = str(func(**arguments))
                        status = "ok"
                except Exception as exc:
                    result_text = f"Error: {exc}"
                    status = "error"
                    name = parsed.get("name", "unknown") if "parsed" in dir() else "unknown"
                results.append(
                    f'<tool_result name="{name}" status="{status}">\n{result_text}\n</tool_result>'
                )

            results_block = "\n".join(results)
            prompt = (
                output + "\n" + results_block + "\n\n"
                "以上是工具返回的结果。请根据结果继续执行任务。\n"
                "如果需要更多数据，请继续输出 <tool_call> 块。\n"
                "如果已完成所有研究，请调用 write_to_file 保存报告，然后输出最终摘要。"
            )
            logger.debug("Tool loop iteration %d: %d calls executed", iteration + 1, len(calls))

        logger.warning("Tool loop reached max iterations (%d)", self.MAX_ITERATIONS)
        return self._strip_tool_calls(last_output)

    def _call_cli(self, prompt):
        """Call the CLI subprocess with the given prompt."""
        try:
            kwargs = dict(
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
                env=self.env,
            )
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            if self.prompt_via == "arg":
                cmd = self.cli_cmd + [prompt]
                kwargs["stdin"] = subprocess.DEVNULL
                result = subprocess.run(cmd, **kwargs)
            else:
                kwargs["input"] = prompt
                result = subprocess.run(self.cli_cmd, **kwargs)
            if result.returncode != 0 and result.stderr:
                logger.warning("CLI stderr: %s", result.stderr[:500])
            return result.stdout
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"CLI subprocess timed out after {self.timeout}s")
        except FileNotFoundError:
            raise RuntimeError(f"CLI command not found: {self.cli_cmd[0]}")

    @staticmethod
    def _strip_tool_calls(text):
        """Remove any remaining <tool_call> blocks from final output."""
        return TOOL_CALL_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class IDEProvider(ABC):
    """Abstract base class for IDE-based LLM providers."""

    name: str = "base"

    @abstractmethod
    def is_available(self):
        """Return True if this provider can be used in the current environment."""

    @abstractmethod
    def create_session(self, system_instruction, tools, use_pro):
        """Prepare a new chat session with the given configuration."""

    @abstractmethod
    def send_message(self, message):
        """Send a message and return the response text."""

    @abstractmethod
    def reset(self):
        """Reset the current session state."""


# ---------------------------------------------------------------------------
# Claude Code Provider
# ---------------------------------------------------------------------------

class ClaudeCodeProvider(IDEProvider):
    """Calls the `claude` CLI (Claude Code) via subprocess.

    Claude Code has built-in tools (WebSearch, Read, Write, Bash, etc.),
    so we do NOT inject a custom <tool_call> protocol.  Instead, we pass the
    workflow instruction + task and let Claude Code handle execution natively.
    """

    name = "claude-code"

    # Tools to pre-approve for Claude Code pipe mode
    _ALLOWED_TOOLS = "Bash Read Write WebSearch WebFetch"
    _PERMISSION_MODE = "bypassPermissions"

    def __init__(self):
        self._system_instruction = None
        self._tool_descriptions = ""
        self._cli_cmd = [
            "claude", "-p",
            "--output-format", "text",
            "--no-session-persistence",
            "--permission-mode", self._PERMISSION_MODE,
            "--allowedTools", self._ALLOWED_TOOLS,
        ]
        self._env = _build_subprocess_env()

    def is_available(self):
        if shutil.which("claude") is None:
            return False
        if sys.platform != "win32":
            return True

        bash_path = self._env.get("CLAUDE_CODE_GIT_BASH_PATH")
        if _git_bash_is_usable(bash_path):
            return True

        logger.warning(
            "Claude provider skipped: unusable Git Bash launcher: %s",
            bash_path or "(unset)",
        )
        return False

    def create_session(self, system_instruction, tools, use_pro):
        self._tool_descriptions = build_tool_descriptions(tools)
        self._system_instruction = system_instruction or ""

    def send_message(self, message):
        prompt_parts = []
        if self._system_instruction:
            prompt_parts.append(self._system_instruction)
        prompt_parts.append("\n---\n## 当前任务\n" + message)
        # Inform Claude Code about project context so it uses its built-in
        # tools (WebSearch, Read, Write, Bash) to fulfil the workflow.
        prompt_parts.append(
            "\n---\n## 执行环境说明\n"
            "你正在 AlphaSystem 项目目录中运行（通过 Claude Code CLI）。\n"
            "请直接使用你的内置工具完成任务：\n"
            "- 用 WebSearch 搜索最新市场信息\n"
            "- 用 Read 读取项目文件（知识库、配置、历史报告）\n"
            "- 用 Write 保存研究报告到 Reports/ 目录\n"
            "- 用 Bash 执行项目脚本（如有需要）\n"
            "不要输出 <tool_call> 标签，直接使用你的原生工具能力。"
        )
        return self._call_cli(prompt_parts)

    def _call_cli(self, prompt_parts):
        """Send prompt to Claude CLI and return output."""
        prompt = "\n\n".join(prompt_parts)
        try:
            kwargs = dict(
                input=prompt,
                capture_output=True,
                text=True,
                timeout=600,
                encoding="utf-8",
                errors="replace",
                env=self._env,
            )
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(self._cli_cmd, **kwargs)
            if result.returncode != 0 and result.stderr:
                logger.warning("Claude CLI stderr: %s", result.stderr[:500])
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            raise TimeoutError("Claude CLI timed out after 600s")
        except FileNotFoundError:
            raise RuntimeError("claude CLI not found in PATH")

    def reset(self):
        self._tool_descriptions = ""
        self._system_instruction = None


# ---------------------------------------------------------------------------
# Codex Provider
# ---------------------------------------------------------------------------

class CodexProvider(IDEProvider):
    """Calls the `codex` CLI via subprocess."""

    name = "codex"

    def __init__(self):
        self._system_instruction = None
        self._tool_map = {}
        self._tool_descriptions = ""
        self._cli_cmd = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
        ]
        self._env = self._build_codex_env()

    def _build_codex_env(self):
        """Route Codex runtime state into the current workspace when possible.

        This avoids hangs/failures when the caller runs inside a sandbox where
        the user profile (for example C:\\Users\\...\\.codex or TEMP) is not
        writable, which is common for automated workflow invocations.
        """
        env = _build_subprocess_env()
        cwd = os.getcwd()
        codex_home = os.path.join(cwd, ".codex_runtime")
        temp_dir = os.path.join(cwd, ".codex_tmp")
        os.makedirs(codex_home, exist_ok=True)
        os.makedirs(temp_dir, exist_ok=True)
        env["CODEX_HOME"] = codex_home
        env["TEMP"] = temp_dir
        env["TMP"] = temp_dir
        return env

    def is_available(self):
        # Avoid recursively launching `codex exec` from inside an active Codex
        # desktop/app session. The nested process often inherits a read-only
        # sandbox and becomes unable to complete write-heavy workflows.
        if os.getenv("CODEX_THREAD_ID") or os.getenv("CODEX_INTERNAL_ORIGINATOR_OVERRIDE"):
            logger.warning("Codex provider skipped inside active Codex session")
            return False
        return shutil.which("codex") is not None

    def create_session(self, system_instruction, tools, use_pro):
        self._tool_map = {f.__name__: f for f in tools} if tools else {}
        self._tool_descriptions = build_tool_descriptions(tools)
        self._system_instruction = system_instruction or ""

    def send_message(self, message):
        if self._tool_map:
            prompt_parts = []
            if self._system_instruction:
                prompt_parts.append(self._system_instruction)
            prompt_parts.append("\n---\n## 当前任务\n" + message)
            prompt_parts.append("\n## Available Tools\n" + self._tool_descriptions)
            prompt_parts.append(TOOL_CALL_PROTOCOL)
            prompt_parts.append(
                "现在请开始执行上面的任务。第一步请调用合适的工具获取数据。"
                "输出 <tool_call> 块后立即停止。"
            )
            full_prompt = "\n\n".join(prompt_parts)
            loop = SubprocessToolLoop(
                self._cli_cmd, self._tool_map, env=self._env, prompt_via="stdin",
            )
            return loop.run(full_prompt)
        else:
            prompt_parts = []
            if self._system_instruction:
                prompt_parts.append(self._system_instruction)
            prompt_parts.append("\n---\n" + message)
            return self._call_simple("\n\n".join(prompt_parts))

    def _call_simple(self, prompt):
        """Single-shot CLI call without tool loop."""
        kwargs = dict(
            input=prompt,
            capture_output=True,
            text=True,
            timeout=600,
            encoding="utf-8",
            errors="replace",
            env=self._env,
        )
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(self._cli_cmd, **kwargs)
        return result.stdout.strip()

    def reset(self):
        self._tool_map = {}
        self._tool_descriptions = ""
        self._system_instruction = None


# ---------------------------------------------------------------------------
# Gemini ADC Provider
# ---------------------------------------------------------------------------

class GeminiADCProvider(IDEProvider):
    """Uses google-genai SDK with Application Default Credentials (no API key)."""

    name = "gemini-adc"

    def __init__(self):
        self._genai = None
        self._types = None
        self._client = None
        self._chat_session = None
        self._model = None

    def is_available(self):
        try:
            from google import genai
            # Try creating a client without API key (ADC)
            genai.Client()
            return True
        except Exception:
            return False

    def create_session(self, system_instruction, tools, use_pro):
        from google import genai
        from google.genai import types

        self._genai = genai
        self._types = types
        self._client = genai.Client()  # ADC — no api_key

        model_free = os.getenv("VPS_MODEL", "gemini-3-flash-preview")
        model_pro = os.getenv("VPS_MODEL_PRO", "gemini-3.1-pro-preview")
        self._model = model_pro if use_pro else model_free

        config_kwargs = {}
        if tools:
            config_kwargs["tools"] = tools
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        self._chat_session = self._client.chats.create(
            model=self._model,
            config=self._types.GenerateContentConfig(**config_kwargs),
        )

    def send_message(self, message):
        if not self._chat_session:
            raise RuntimeError("GeminiADCProvider: no active session, call create_session first")
        response = self._chat_session.send_message(message)
        return self._extract_text(response)

    @staticmethod
    def _parts_to_text(parts):
        """Join text-bearing parts before falling back to response.text."""
        if not parts:
            return None

        chunks = []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)

        return "".join(chunks) if chunks else None

    def _extract_text(self, response):
        """Extract text from Gemini response."""
        if hasattr(response, "parts") and response.parts:
            text = self._parts_to_text(response.parts)
            if text:
                return text

        if hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None)
                text = self._parts_to_text(parts)
                if text:
                    return text

        try:
            return response.text
        except Exception:
            return None
        return None

    def reset(self):
        self._chat_session = None


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

def detect_provider(forced=None):
    """Detect and return an available IDE provider.

    Args:
        forced: Provider name to force ("claude", "codex", "gemini-adc"),
                or "auto" to try in order. Defaults to IDE_PROVIDER env var.

    Returns:
        An IDEProvider instance, or None if no provider is available.
    """
    name = forced or os.getenv("IDE_PROVIDER", "auto")

    provider_map = {
        "claude": ClaudeCodeProvider,
        "codex": CodexProvider,
        "gemini-adc": GeminiADCProvider,
    }

    if name in provider_map:
        provider = provider_map[name]()
        if provider.is_available():
            logger.info("IDE provider forced: %s", name)
            return provider
        logger.warning("Forced IDE provider '%s' is not available", name)
        return None

    if name == "auto":
        for provider_cls in [ClaudeCodeProvider, CodexProvider, GeminiADCProvider]:
            try:
                p = provider_cls()
                if p.is_available():
                    logger.info("Auto-detected IDE provider: %s", p.name)
                    return p
            except Exception:
                continue

    return None
