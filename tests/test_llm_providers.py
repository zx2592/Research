"""
Tests for core/llm_providers.py — OpenAI-compatible providers + tool loop.
"""
from types import SimpleNamespace

import pytest

from core.llm_providers import (
    OPENAI_COMPATIBLE_PROVIDERS,
    OpenAICompatibleProvider,
    build_openai_tools,
    resolve_provider,
)
from core.llm_client import LLMClient, LLMConfigError


# --- OpenAI response fakes ------------------------------------------------

def _tool_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def _response(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _ScriptedOpenAIClient:
    """Returns a programmed sequence of responses; records create() kwargs."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class TestResolveProvider:
    def test_default_is_gemini(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        assert resolve_provider() == "gemini"

    def test_respects_env_with_case_and_whitespace(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "  OpenRouter  ")
        assert resolve_provider() == "openrouter"


class TestProviderConfigTable:
    def test_three_providers_registered(self):
        assert set(OPENAI_COMPATIBLE_PROVIDERS) == {"openai", "openrouter", "qwen"}

    def test_openrouter_and_qwen_have_base_urls(self):
        assert OPENAI_COMPATIBLE_PROVIDERS["openrouter"]["base_url"].endswith("openrouter.ai/api/v1")
        assert "dashscope" in OPENAI_COMPATIBLE_PROVIDERS["qwen"]["base_url"]

    def test_openai_uses_sdk_default_base_url(self):
        assert OPENAI_COMPATIBLE_PROVIDERS["openai"]["base_url"] is None


class TestBuildOpenAITools:
    def test_schema_from_signature_and_docstring(self):
        def sample(query: str, limit: int = 10, *args, **kwargs) -> str:
            """Do a search."""
            return ""

        schemas, tool_map = build_openai_tools([sample])
        fn = schemas[0]["function"]
        assert fn["name"] == "sample"
        assert fn["description"] == "Do a search."
        props = fn["parameters"]["properties"]
        assert props["query"] == {"type": "string"}
        assert props["limit"] == {"type": "integer"}
        # variadic params are skipped
        assert "args" not in props and "kwargs" not in props
        # only params without defaults are required
        assert fn["parameters"]["required"] == ["query"]
        assert tool_map["sample"] is sample

    def test_unannotated_param_defaults_to_string(self):
        def f(x):
            return ""

        schemas, _ = build_openai_tools([f])
        assert schemas[0]["function"]["parameters"]["properties"]["x"] == {"type": "string"}


class TestOpenAICompatibleProvider:
    def test_unknown_provider_raises(self):
        with pytest.raises(LLMConfigError, match="Unknown OpenAI-compatible provider"):
            OpenAICompatibleProvider("anthropic")

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(LLMConfigError, match="No API key for provider 'openai'"):
            OpenAICompatibleProvider("openai")

    def test_model_defaults_and_env_override(self, monkeypatch):
        monkeypatch.setenv("QWEN_API_KEY", "fake-qwen-key")
        monkeypatch.delenv("QWEN_MODEL", raising=False)
        monkeypatch.delenv("QWEN_MODEL_PRO", raising=False)
        p = OpenAICompatibleProvider("qwen")
        assert p.model_free == "qwen-plus"
        assert p.model_pro == "qwen-max"
        assert "dashscope" in p.base_url

        monkeypatch.setenv("QWEN_MODEL", "qwen-turbo")
        p2 = OpenAICompatibleProvider("qwen")
        assert p2.model_free == "qwen-turbo"

    def test_qwen_falls_back_to_dashscope_key(self, monkeypatch):
        monkeypatch.delenv("QWEN_API_KEY", raising=False)
        monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-dashscope-key")
        p = OpenAICompatibleProvider("qwen")
        assert p.api_key == "fake-dashscope-key"

    def test_text_chat_round_trip(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        p = OpenAICompatibleProvider("openai")
        p._client = _ScriptedOpenAIClient([_response(content="text reply")])
        p.create_session(system_instruction="you are a bot")

        result = p.chat("hello")

        assert result == "text reply"
        roles = [m["role"] for m in p._messages]
        assert roles == ["system", "user", "assistant"]
        assert p._client.calls[0]["model"] == "gpt-4o-mini"
        assert "tools" not in p._client.calls[0]

    def test_reset_keeps_system_message(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        p = OpenAICompatibleProvider("openai")
        p._client = _ScriptedOpenAIClient([_response(content="hi")])
        p.create_session(system_instruction="sys")
        p.chat("hello")
        p.reset()
        assert p._messages == [{"role": "system", "content": "sys"}]


class TestToolLoop:
    def _provider(self, monkeypatch, responses):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        p = OpenAICompatibleProvider("openai")
        p._client = _ScriptedOpenAIClient(responses)
        return p

    def test_executes_tool_then_returns_final_text(self, monkeypatch):
        seen = []

        def search_web(query: str) -> str:
            seen.append(query)
            return "TOOL:" + query

        p = self._provider(
            monkeypatch,
            [
                _response(tool_calls=[_tool_call("c1", "search_web", '{"query": "NVDA"}')]),
                _response(content="final answer"),
            ],
        )
        p.create_session(system_instruction="sys", tools=[search_web])

        result = p.chat("research NVDA")

        assert result == "final answer"
        assert seen == ["NVDA"]
        roles = [m["role"] for m in p._messages]
        assert roles == ["system", "user", "assistant", "tool", "assistant"]
        # first turn must offer tools
        assert p._client.calls[0]["tools"]
        assert p._client.calls[0]["tool_choice"] == "auto"
        # tool result fed back with the matching id
        tool_msg = next(m for m in p._messages if m["role"] == "tool")
        assert tool_msg["tool_call_id"] == "c1"
        assert tool_msg["content"] == "TOOL:NVDA"

    def test_unknown_tool_reported_gracefully(self, monkeypatch):
        def search_web(query: str) -> str:
            return "ok"

        p = self._provider(
            monkeypatch,
            [
                _response(tool_calls=[_tool_call("c1", "does_not_exist", "{}")]),
                _response(content="recovered"),
            ],
        )
        p.create_session(tools=[search_web])

        result = p.chat("go")

        assert result == "recovered"
        tool_msg = next(m for m in p._messages if m["role"] == "tool")
        assert "unknown tool" in tool_msg["content"]

    def test_tool_raising_is_caught(self, monkeypatch):
        def search_web(query: str) -> str:
            raise RuntimeError("boom")

        p = self._provider(
            monkeypatch,
            [
                _response(tool_calls=[_tool_call("c1", "search_web", '{"query": "x"}')]),
                _response(content="handled"),
            ],
        )
        p.create_session(tools=[search_web])

        assert p.chat("go") == "handled"
        tool_msg = next(m for m in p._messages if m["role"] == "tool")
        assert "Error: boom" in tool_msg["content"]

    def test_max_iterations_guard(self, monkeypatch):
        def search_web(query: str = "") -> str:
            return "again"

        # always asks for a tool call; loop must stop and force a summary
        loop_resps = [
            _response(tool_calls=[_tool_call(f"c{i}", "search_web", "{}")]) for i in range(2)
        ]
        p = self._provider(monkeypatch, loop_resps + [_response(content="forced summary")])
        p._max_iterations = 2
        p.create_session(tools=[search_web])

        assert p.chat("go") == "forced summary"


class TestLLMClientProviderRouting:
    def test_routes_through_oai(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "qwen")
        monkeypatch.setenv("QWEN_API_KEY", "fake-qwen-key")
        client = LLMClient()

        assert client.provider == "qwen"
        assert client.mode == "vps"
        assert client._oai is not None
        assert client.model_free == "qwen-plus"

    def test_text_chat(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        client = LLMClient()
        client._oai._client = _ScriptedOpenAIClient([_response(content="routed reply")])
        client.create_chat()  # no tools

        assert client.chat("hello") == "routed reply"

    def test_tool_loop_via_llmclient(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        client = LLMClient()
        client._oai._client = _ScriptedOpenAIClient(
            [
                _response(tool_calls=[_tool_call("c1", "search_web", '{"query": "x"}')]),
                _response(content="done"),
            ]
        )

        def search_web(query: str) -> str:
            return "R:" + query

        client.create_chat(tools=[search_web])
        assert client.chat("go") == "done"

    def test_chat_error_is_caught(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        client = LLMClient()

        class _Boom:
            chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_: (_ for _ in ()).throw(RuntimeError("api down"))
                )
            )

        client._oai._client = _Boom()
        client.create_chat()
        result = client.chat("hello")
        assert result.startswith("Error:")
