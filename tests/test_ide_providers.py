"""
Tests for core/ide_providers.py — IDE provider abstraction layer.
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.ide_providers import (
    TOOL_CALL_RE,
    ClaudeCodeProvider,
    CodexProvider,
    GeminiADCProvider,
    SubprocessToolLoop,
    build_tool_descriptions,
    detect_provider,
    _resolve_git_bash,
)


class _ResponseTextTrap:
    def __init__(self, parts=None, candidates=None, fallback_text=None):
        self.parts = parts
        self.candidates = candidates
        self._fallback_text = fallback_text

    @property
    def text(self):
        if self._fallback_text is None:
            raise AssertionError("response.text should not be accessed")
        return self._fallback_text


# ---------------------------------------------------------------------------
# build_tool_descriptions
# ---------------------------------------------------------------------------

class TestBuildToolDescriptions:
    def test_empty_tools(self):
        assert build_tool_descriptions([]) == ""
        assert build_tool_descriptions(None) == ""

    def test_single_callable(self):
        def search_web(query: str) -> str:
            """Search the web for latest information."""
            pass

        result = build_tool_descriptions([search_web])
        assert "search_web" in result
        assert "query" in result
        assert "Search the web" in result

    def test_multiple_callables(self):
        def tool_a(x: int) -> str:
            """Tool A doc."""
            pass

        def tool_b(y: str, z: bool = False) -> str:
            """Tool B doc."""
            pass

        result = build_tool_descriptions([tool_a, tool_b])
        assert "tool_a" in result
        assert "tool_b" in result
        assert "Tool A doc" in result
        assert "Tool B doc" in result

    def test_callable_without_docstring(self):
        def no_doc(x: int):
            pass

        result = build_tool_descriptions([no_doc])
        assert "no_doc" in result


# ---------------------------------------------------------------------------
# TOOL_CALL_RE regex
# ---------------------------------------------------------------------------

class TestToolCallRegex:
    def test_single_tool_call(self):
        text = '<tool_call>\n{"name": "search", "arguments": {"q": "test"}}\n</tool_call>'
        matches = TOOL_CALL_RE.findall(text)
        assert len(matches) == 1
        parsed = json.loads(matches[0])
        assert parsed["name"] == "search"
        assert parsed["arguments"]["q"] == "test"

    def test_multiple_tool_calls(self):
        text = (
            'Some text\n'
            '<tool_call>\n{"name": "a", "arguments": {}}\n</tool_call>\n'
            'Middle text\n'
            '<tool_call>\n{"name": "b", "arguments": {"x": 1}}\n</tool_call>\n'
            'End text'
        )
        matches = TOOL_CALL_RE.findall(text)
        assert len(matches) == 2
        assert json.loads(matches[0])["name"] == "a"
        assert json.loads(matches[1])["name"] == "b"

    def test_no_tool_calls(self):
        text = "This is a plain response with no tool calls."
        matches = TOOL_CALL_RE.findall(text)
        assert len(matches) == 0


# ---------------------------------------------------------------------------
# SubprocessToolLoop
# ---------------------------------------------------------------------------

class TestSubprocessToolLoop:
    def test_no_tool_calls_returns_output(self):
        """When CLI output has no <tool_call>, return it directly."""
        loop = SubprocessToolLoop(
            cli_cmd=["echo"],
            tool_map={},
        )
        with patch.object(loop, "_call_cli", return_value="Final answer."):
            result = loop.run("initial prompt")
        assert result == "Final answer."

    def test_tool_call_executes_and_continues(self):
        """Tool calls are executed and results fed back."""
        call_count = {"n": 0}

        def mock_cli(prompt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return '<tool_call>\n{"name": "add", "arguments": {"a": 1, "b": 2}}\n</tool_call>'
            else:
                return "Result is 3."

        def add(a, b):
            return str(a + b)

        loop = SubprocessToolLoop(
            cli_cmd=["fake"],
            tool_map={"add": add},
        )
        with patch.object(loop, "_call_cli", side_effect=mock_cli):
            result = loop.run("What is 1+2?")

        assert result == "Result is 3."
        assert call_count["n"] == 2

    def test_max_iterations_stops(self):
        """Loop should stop after MAX_ITERATIONS."""
        def always_tool_call(prompt):
            return '<tool_call>\n{"name": "noop", "arguments": {}}\n</tool_call>'

        def noop():
            return "ok"

        loop = SubprocessToolLoop(
            cli_cmd=["fake"],
            tool_map={"noop": noop},
        )
        loop.MAX_ITERATIONS = 3  # Lower for test speed

        with patch.object(loop, "_call_cli", side_effect=always_tool_call):
            result = loop.run("start")

        # Should have been called exactly MAX_ITERATIONS times
        assert result == ""  # tool_call blocks stripped

    def test_unknown_tool_returns_error(self):
        """Unknown tool name should produce error result, not crash."""
        call_count = {"n": 0}

        def mock_cli(prompt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return '<tool_call>\n{"name": "unknown_fn", "arguments": {}}\n</tool_call>'
            else:
                return "I got an error for unknown_fn."

        loop = SubprocessToolLoop(
            cli_cmd=["fake"],
            tool_map={},
        )
        with patch.object(loop, "_call_cli", side_effect=mock_cli):
            result = loop.run("test")

        assert "error" in result.lower() or "unknown" in result.lower() or result == "I got an error for unknown_fn."


# ---------------------------------------------------------------------------
# _resolve_git_bash
# ---------------------------------------------------------------------------

class TestResolveGitBash:
    def test_none_input(self):
        assert _resolve_git_bash(None) is None

    def test_usr_bin_resolved_to_bin(self, tmp_path):
        """Git\\usr\\bin\\bash.exe should resolve to Git\\bin\\bash.exe."""
        git_root = tmp_path / "Git"
        (git_root / "usr" / "bin").mkdir(parents=True)
        (git_root / "bin").mkdir(parents=True)
        usr_bash = git_root / "usr" / "bin" / "bash.exe"
        bin_bash = git_root / "bin" / "bash.exe"
        usr_bash.touch()
        bin_bash.touch()
        result = _resolve_git_bash(str(usr_bash))
        assert result == str(bin_bash)

    def test_bin_path_returned_directly(self, tmp_path):
        """Git\\bin\\bash.exe should be returned as-is."""
        git_root = tmp_path / "Git"
        (git_root / "bin").mkdir(parents=True)
        bin_bash = git_root / "bin" / "bash.exe"
        bin_bash.touch()
        result = _resolve_git_bash(str(bin_bash))
        assert result == str(bin_bash)

    def test_non_git_path_returns_none(self):
        assert _resolve_git_bash("/usr/bin/bash") is None


# ---------------------------------------------------------------------------
# Provider availability
# ---------------------------------------------------------------------------

class TestProviderAvailability:
    def test_claude_provider_available_when_cli_exists(self):
        provider = ClaudeCodeProvider()
        with patch("core.ide_providers.shutil.which", return_value="/usr/bin/claude"), \
             patch("core.ide_providers.sys.platform", "linux"):
            assert provider.is_available() is True

    def test_claude_provider_unavailable(self):
        provider = ClaudeCodeProvider()
        with patch("core.ide_providers.shutil.which", return_value=None):
            assert provider.is_available() is False

    def test_codex_provider_available_when_cli_exists(self):
        provider = CodexProvider()
        with patch.dict("os.environ", {}, clear=False), \
             patch("core.ide_providers.shutil.which", return_value="/usr/bin/codex"):
            os.environ.pop("CODEX_THREAD_ID", None)
            os.environ.pop("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", None)
            assert provider.is_available() is True

    def test_codex_provider_unavailable(self):
        provider = CodexProvider()
        with patch("core.ide_providers.shutil.which", return_value=None):
            assert provider.is_available() is False

    def test_codex_provider_unavailable_inside_active_codex_session(self, monkeypatch):
        provider = CodexProvider()
        monkeypatch.setenv("CODEX_THREAD_ID", "thread-123")
        with patch("core.ide_providers.shutil.which", return_value="/usr/bin/codex"):
            assert provider.is_available() is False

    def test_gemini_adc_provider_unavailable_without_sdk(self):
        """Without google-genai SDK or ADC, should return False."""
        provider = GeminiADCProvider()
        with patch.dict("sys.modules", {"google": None, "google.genai": None}):
            assert provider.is_available() is False


class TestGeminiADCResponseExtraction:
    def test_extract_text_prefers_parts_before_text_property(self):
        provider = GeminiADCProvider()
        response = _ResponseTextTrap(
            parts=[SimpleNamespace(text="hello"), SimpleNamespace(text=" world")]
        )

        assert provider._extract_text(response) == "hello world"


# ---------------------------------------------------------------------------
# detect_provider
# ---------------------------------------------------------------------------

class TestDetectProvider:
    def test_auto_detection_order(self):
        """Auto mode tries Claude → Codex → Gemini ADC in order."""
        with patch.object(ClaudeCodeProvider, "is_available", return_value=True):
            result = detect_provider("auto")
        assert result is not None
        assert result.name == "claude-code"

    def test_auto_skips_unavailable(self):
        """Auto mode skips unavailable providers."""
        with patch.object(ClaudeCodeProvider, "is_available", return_value=False), \
             patch.object(CodexProvider, "is_available", return_value=True):
            result = detect_provider("auto")
        assert result is not None
        assert result.name == "codex"

    def test_auto_returns_none_when_all_unavailable(self):
        with patch.object(ClaudeCodeProvider, "is_available", return_value=False), \
             patch.object(CodexProvider, "is_available", return_value=False), \
             patch.object(GeminiADCProvider, "is_available", return_value=False):
            result = detect_provider("auto")
        assert result is None

    def test_forced_provider(self):
        with patch.object(ClaudeCodeProvider, "is_available", return_value=True):
            result = detect_provider("claude")
        assert result is not None
        assert result.name == "claude-code"

    def test_forced_provider_unavailable_returns_none(self):
        with patch.object(CodexProvider, "is_available", return_value=False):
            result = detect_provider("codex")
        assert result is None

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("IDE_PROVIDER", "codex")
        with patch.object(CodexProvider, "is_available", return_value=True):
            result = detect_provider()  # No forced= arg, reads env
        assert result is not None
        assert result.name == "codex"


# ---------------------------------------------------------------------------
# SubprocessToolLoop prompt_via="arg"
# ---------------------------------------------------------------------------

class TestSubprocessToolLoopArgMode:
    def test_arg_mode_no_tool_calls(self):
        """In arg mode, prompt is passed as CLI argument, not stdin."""
        loop = SubprocessToolLoop(
            cli_cmd=["fake"],
            tool_map={},
            prompt_via="arg",
        )
        with patch("core.ide_providers.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="Final answer.", returncode=0, stderr=""
            )
            result = loop.run("hello world")

        # Should have been called with prompt appended as arg
        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", call_args[0])
        assert cmd == ["fake", "hello world"]
        assert call_args[1].get("input") is None  # No stdin input
        assert result == "Final answer."

    def test_arg_mode_tool_loop(self):
        """Arg mode still works for multi-turn tool-calling."""
        call_count = {"n": 0}

        def mock_cli(prompt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return '<tool_call>\n{"name": "greet", "arguments": {"name": "Alice"}}\n</tool_call>'
            return "Hello Alice!"

        def greet(name):
            return f"Hi {name}!"

        loop = SubprocessToolLoop(
            cli_cmd=["fake"],
            tool_map={"greet": greet},
            prompt_via="arg",
        )
        with patch.object(loop, "_call_cli", side_effect=mock_cli):
            result = loop.run("Say hello to Alice")

        assert result == "Hello Alice!"
        assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# Codex provider uses stdin mode
# ---------------------------------------------------------------------------

class TestCodexProviderPromptMode:
    def test_codex_send_message_uses_stdin_mode(self):
        """CodexProvider should stream long prompts via stdin, not argv."""
        provider = CodexProvider()
        provider.create_session(
            system_instruction="You are helpful.",
            tools=[lambda: None],
            use_pro=False,
        )

        with patch("core.ide_providers.SubprocessToolLoop") as MockLoop:
            mock_instance = MagicMock()
            mock_instance.run.return_value = "Done."
            MockLoop.return_value = mock_instance
            provider.send_message("test task")

        MockLoop.assert_called_once()
        _, kwargs = MockLoop.call_args
        assert kwargs.get("prompt_via") == "stdin"

    def test_codex_provider_uses_workspace_write_ephemeral_mode(self):
        """CodexProvider should avoid readonly sandbox/state-dir issues in workflows."""
        provider = CodexProvider()
        assert "--ephemeral" in provider._cli_cmd
        assert "--sandbox" in provider._cli_cmd
        assert "workspace-write" in provider._cli_cmd


# ---------------------------------------------------------------------------
# Desktop mode reset integration
# ---------------------------------------------------------------------------

class TestDesktopSessionReset:
    def test_llm_client_reset_clears_ide_provider(self):
        """LLMClient.reset() should reset both chat_session and IDE provider."""
        from core.llm_client import LLMClient

        client = LLMClient(force_mode="desktop")
        mock_provider = MagicMock()
        mock_provider.name = "test-provider"
        client._ide_provider = mock_provider

        client.chat_session = "fake-session"
        client.reset()

        assert client.chat_session is None
        mock_provider.reset.assert_called_once()

    def test_claude_provider_reset_clears_state(self):
        """ClaudeCodeProvider.reset() should clear descriptions and system instruction."""
        provider = ClaudeCodeProvider()
        provider.create_session(
            system_instruction="System prompt",
            tools=[lambda: None],
            use_pro=False,
        )
        assert provider._system_instruction

        provider.reset()

        assert provider._tool_descriptions == ""
        assert provider._system_instruction is None


# ---------------------------------------------------------------------------
# Claude Code uses native tools, not SubprocessToolLoop
# ---------------------------------------------------------------------------

class TestClaudeCodeNativeTools:
    def test_claude_provider_does_not_use_tool_loop(self):
        """ClaudeCodeProvider should NOT use SubprocessToolLoop."""
        provider = ClaudeCodeProvider()
        provider.create_session(
            system_instruction="Test",
            tools=[lambda: None],
            use_pro=False,
        )
        with patch("core.ide_providers.SubprocessToolLoop") as MockLoop, \
             patch.object(provider, "_call_cli", return_value="Done."):
            provider.send_message("test")
        MockLoop.assert_not_called()

    def test_claude_provider_output_includes_env_note(self):
        """Prompt sent to Claude CLI should include execution env instructions."""
        provider = ClaudeCodeProvider()
        provider.create_session(
            system_instruction="Workflow content",
            tools=[lambda: None],
            use_pro=False,
        )
        captured_parts = {}

        def capture_call(prompt_parts):
            captured_parts["prompt"] = "\n\n".join(prompt_parts)
            return "Result text."

        with patch.object(provider, "_call_cli", side_effect=capture_call):
            provider.send_message("Do research on AAPL")

        prompt = captured_parts["prompt"]
        assert "WebSearch" in prompt
        assert "当前任务" in prompt
        assert "Workflow content" in prompt


# ---------------------------------------------------------------------------
# Tools completeness (integration)
# ---------------------------------------------------------------------------

class TestToolsCompleteness:
    def test_research_agent_tools_include_file_ops(self):
        """ResearchAgent._tools() must include read_file and list_dir."""
        # V3.9: _tools() now delegates to ToolFactory.get_tools().
        # Inspect ToolFactory source for the return list.
        import ast
        import os

        factory_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "core", "tool_factory.py",
        )
        with open(factory_path, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        # Find the get_tools method
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_tools":
                for child in ast.walk(node):
                    if isinstance(child, ast.Return) and isinstance(child.value, ast.List):
                        tool_names = []
                        for elt in child.value.elts:
                            if isinstance(elt, ast.Attribute):
                                tool_names.append(elt.attr)
                            elif isinstance(elt, ast.Name):
                                tool_names.append(elt.id)
                        assert "read_file" in tool_names, "read_file missing from get_tools()"
                        assert "list_dir" in tool_names, "list_dir missing from get_tools()"
                        assert "search_web" in tool_names
                        assert "write_to_file" in tool_names
                        return

        pytest.fail("Could not find get_tools() return list in core/tool_factory.py")


class TestClaudeCodeBatchFlags:
    def test_claude_provider_uses_non_persistent_batch_flags(self):
        """Claude provider should use print-and-exit flags suitable for batch runs."""
        provider = ClaudeCodeProvider()
        assert "--no-session-persistence" in provider._cli_cmd
        assert "--permission-mode" in provider._cli_cmd
        assert "bypassPermissions" in provider._cli_cmd
