"""
Tests for core/llm_client.py - LLMClient configuration and key routing.
"""
import os
from types import SimpleNamespace
import pytest

from core.llm_client import LLMClient, LLMConfigError


class TestLLMClientMode:
    def test_mode_is_always_vps(self, monkeypatch):
        """The client is API-driven only — mode is always 'vps'."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
        try:
            import google.genai  # noqa: F401
        except ImportError:
            pytest.skip("google-genai not installed")
        client = LLMClient()
        assert client.mode == "vps"

    def test_vps_mode_without_key_raises(self, monkeypatch):
        """VPS mode without API key should raise LLMConfigError, not sys.exit."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY_BACKUP", raising=False)
        try:
            import google.genai  # noqa: F401
        except ImportError:
            pytest.skip("google-genai not installed")
        with pytest.raises(LLMConfigError, match="GEMINI_API_KEY"):
            LLMClient()

    def test_load_system_instruction_reads_file(self, tmp_dir):
        """load_system_instruction should populate system_instruction from file."""
        filepath = os.path.join(tmp_dir, "test_prompt.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("You are a helpful assistant.")
        client = object.__new__(LLMClient)
        client.system_instruction = None
        client.load_system_instruction(filepath)
        assert client.system_instruction == "You are a helpful assistant."

    def test_load_system_instruction_missing_file(self):
        """Missing file should not raise, system_instruction stays None."""
        client = object.__new__(LLMClient)
        client.system_instruction = None
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
        client = object.__new__(LLMClient)
        client.mode = "vps"
        client.provider = "gemini"
        client.chat_session = None
        client.client_active = None
        client.active_api_label = None
        client.active_model = None
        client._chat_tools = None
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
