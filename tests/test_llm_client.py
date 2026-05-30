"""
Tests for core/llm_client.py - LLMClient configuration and key routing.
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.llm_client import LLMClient, LLMConfigError


class TestLLMClientModeDetection:
    def test_detect_mode_defaults_to_desktop_without_key(self, monkeypatch):
        """Without env vars and no API key, default mode is desktop."""
        monkeypatch.delenv("LLM_MODE", raising=False)
        monkeypatch.delenv("RUNNING_AS_BOT", raising=False)
        monkeypatch.delenv("RUNNING_AS_SENTINEL", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY_BACKUP", raising=False)
        client = LLMClient(force_mode=None)
        assert client.mode == "desktop"

    def test_detect_mode_auto_vps_when_key_exists(self, monkeypatch):
        """With GEMINI_API_KEY + non-Windows + no IDE CLI → vps."""
        monkeypatch.delenv("LLM_MODE", raising=False)
        monkeypatch.delenv("RUNNING_AS_BOT", raising=False)
        monkeypatch.delenv("RUNNING_AS_SENTINEL", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
        monkeypatch.setattr("core.llm_client.shutil.which", lambda _: None)
        monkeypatch.setattr("core.llm_client.sys.platform", "linux")
        client = LLMClient(force_mode="desktop")
        assert client._detect_mode() == "vps"

    def test_detect_mode_desktop_when_ide_available(self, monkeypatch):
        """With GEMINI_API_KEY present but claude CLI on PATH → desktop."""
        monkeypatch.delenv("LLM_MODE", raising=False)
        monkeypatch.delenv("RUNNING_AS_BOT", raising=False)
        monkeypatch.delenv("RUNNING_AS_SENTINEL", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
        monkeypatch.setattr(
            "core.llm_client.shutil.which",
            lambda cmd: "/usr/local/bin/claude" if cmd == "claude" else None,
        )
        client = LLMClient(force_mode="desktop")
        assert client._detect_mode() == "desktop"

    def test_detect_mode_desktop_on_windows(self, monkeypatch):
        """Windows platform + no IDE CLI + has GEMINI_API_KEY → desktop."""
        monkeypatch.delenv("LLM_MODE", raising=False)
        monkeypatch.delenv("RUNNING_AS_BOT", raising=False)
        monkeypatch.delenv("RUNNING_AS_SENTINEL", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
        monkeypatch.setattr("core.llm_client.shutil.which", lambda _: None)
        monkeypatch.setattr("core.llm_client.sys.platform", "win32")
        client = LLMClient(force_mode="desktop")
        assert client._detect_mode() == "desktop"

    def test_detect_mode_respects_env_var(self, monkeypatch):
        """LLM_MODE=vps should set mode to vps (without actually initialising API)."""
        monkeypatch.setenv("LLM_MODE", "vps")
        client = LLMClient(force_mode="desktop")
        client2_mode = client._detect_mode()
        assert client2_mode == "vps"

    def test_force_mode_overrides_detection(self, monkeypatch):
        monkeypatch.setenv("LLM_MODE", "vps")
        client = LLMClient(force_mode="desktop")
        assert client.mode == "desktop"

    def test_vps_mode_without_key_raises(self, monkeypatch):
        """VPS mode without API key should raise LLMConfigError, not sys.exit."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY_BACKUP", raising=False)
        try:
            import google.genai  # noqa: F401
        except ImportError:
            pytest.skip("google-genai not installed")
        with pytest.raises(LLMConfigError, match="GEMINI_API_KEY"):
            LLMClient(force_mode="vps")

    def test_desktop_mode_no_crash(self, monkeypatch):
        """Desktop mode initialisation should not raise."""
        monkeypatch.delenv("LLM_MODE", raising=False)
        client = LLMClient(force_mode="desktop")
        assert client.mode == "desktop"
        assert client.client is None

    def test_load_system_instruction_reads_file(self, tmp_dir):
        """load_system_instruction should populate system_instruction from file."""
        filepath = os.path.join(tmp_dir, "test_prompt.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("You are a helpful assistant.")
        client = LLMClient(force_mode="desktop")
        client.load_system_instruction(filepath)
        assert client.system_instruction == "You are a helpful assistant."

    def test_load_system_instruction_missing_file(self):
        """Missing file should not raise, system_instruction stays None."""
        client = LLMClient(force_mode="desktop")
        client.load_system_instruction("/nonexistent/path/prompt.md")
        assert client.system_instruction is None


class _FakeChatSession:
    def __init__(self, responses):
        self._responses = list(responses)

    def send_message(self, _message):
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeGeminiClient:
    def __init__(self, api_key, sessions_by_key):
        self.api_key = api_key
        self._sessions_by_key = sessions_by_key
        self.chats = SimpleNamespace(create=self._create_chat)

    def _create_chat(self, model, config):
        session_or_error = self._sessions_by_key[self.api_key]
        if isinstance(session_or_error, Exception):
            raise session_or_error
        return session_or_error


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


class TestLLMClientKeyRouting:
    def _make_vps_client(self, sessions_by_key):
        client = LLMClient(force_mode="desktop")
        client.mode = "vps"
        client.api_key = "primary-key"
        client.api_key_backup = "backup-key"
        client.model_free = "gemini-3-flash-preview"
        client.model_pro = "gemini-3.1-pro-preview"
        client.system_instruction = "system"
        client._types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)

        created_keys = []

        def client_factory(api_key, vertexai=False):
            assert vertexai is False
            created_keys.append(api_key)
            return _FakeGeminiClient(api_key, sessions_by_key)

        client._genai = SimpleNamespace(Client=client_factory)
        return client, created_keys

    def test_create_chat_prefers_primary_key_for_flash(self):
        sessions = {
            "primary-key": _FakeChatSession([SimpleNamespace(text="ok")]),
            "backup-key": _FakeChatSession([SimpleNamespace(text="unused")]),
        }
        client, created_keys = self._make_vps_client(sessions)

        client.create_chat(use_pro=False)

        assert created_keys == ["primary-key"]
        assert client.active_api_label == "primary"

    def test_chat_falls_back_to_backup_when_primary_send_fails(self):
        sessions = {
            "primary-key": _FakeChatSession([RuntimeError("quota exceeded")]),
            "backup-key": _FakeChatSession([SimpleNamespace(text="backup success")]),
        }
        client, created_keys = self._make_vps_client(sessions)

        result = client.chat("hello", tools=["tool"], use_pro=False)

        assert result == "backup success"
        assert created_keys == ["primary-key", "backup-key"]
        assert client.active_api_label == "backup"


class TestLLMClientDesktopMode:
    def test_desktop_mode_init_calls_init_desktop(self, monkeypatch):
        """Desktop mode __init__ should call _init_desktop and set _ide_provider."""
        monkeypatch.delenv("IDE_PROVIDER", raising=False)
        client = LLMClient(force_mode="desktop")
        assert client.mode == "desktop"
        assert hasattr(client, "_ide_provider")
        assert hasattr(client, "_vps_fallback_ready")

    def test_desktop_chat_uses_ide_provider(self):
        """When IDE provider is available, chat() should use it."""
        client = LLMClient(force_mode="desktop")
        mock_provider = MagicMock()
        mock_provider.name = "test-provider"
        mock_provider.send_message.return_value = "IDE response"
        client._ide_provider = mock_provider
        client._vps_fallback_ready = False
        client._desktop_tools = None

        result = client.chat("hello")

        assert result == "IDE response"
        mock_provider.send_message.assert_called_once_with("hello")

    def test_desktop_chat_fallback_on_failure(self, monkeypatch):
        """When IDE provider raises, fallback message should indicate failure."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY_BACKUP", raising=False)
        client = LLMClient(force_mode="desktop")
        mock_provider = MagicMock()
        mock_provider.name = "broken-provider"
        mock_provider.send_message.side_effect = RuntimeError("CLI crashed")
        client._ide_provider = mock_provider
        client._vps_fallback_ready = False
        client._desktop_tools = None

        result = client.chat("hello")

        assert "Error" in result or "error" in result.lower()


class TestLLMClientResponseExtraction:
    def test_extract_response_text_prefers_parts_before_text_property(self):
        client = object.__new__(LLMClient)
        response = _ResponseTextTrap(
            parts=[SimpleNamespace(text="hello"), SimpleNamespace(text=" world")]
        )

        assert client._extract_response_text(response) == "hello world"

    def test_extract_response_text_uses_candidate_parts_before_text_property(self):
        client = object.__new__(LLMClient)
        response = _ResponseTextTrap(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[SimpleNamespace(text="candidate text")]
                    )
                )
            ]
        )

        assert client._extract_response_text(response) == "candidate text"
