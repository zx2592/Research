#!/usr/bin/env python3
"""OpenAI-compatible LLM providers.

Gemini remains the default (see core/llm_client.py). This module adds
support for OpenAI-compatible chat APIs:

  - openai      → https://api.openai.com/v1
  - openrouter  → https://openrouter.ai/api/v1
  - qwen        → https://dashscope.aliyuncs.com/compatible-mode/v1  (DashScope)

Selected via the ``LLM_PROVIDER`` env var (default ``gemini``). All three
share one OpenAI-compatible adapter — only base_url / key / model differ.

Both plain-text chat and tool/function calling are implemented. Tools are the
same Python callables used by Gemini (from ToolFactory); they are converted to
OpenAI JSON-schema tool definitions and driven through a manual tool-calling
loop (request → tool_calls → execute → feed results back → repeat).
"""

import inspect
import json
import logging
import os

from core import config, settings
from core.llm_client import LLMConfigError

logger = logging.getLogger(__name__)


# provider name -> connection + model defaults (all overridable via env)
OPENAI_COMPATIBLE_PROVIDERS = {
    "openai": {
        "base_url": None,  # use OpenAI SDK default (https://api.openai.com/v1)
        "key_envs": ("OPENAI_API_KEY",),
        "model_env": "OPENAI_MODEL",
        "model_pro_env": "OPENAI_MODEL_PRO",
        "default_model": "gpt-4o-mini",
        "default_model_pro": "gpt-4o",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_envs": ("OPENROUTER_API_KEY",),
        "model_env": "OPENROUTER_MODEL",
        "model_pro_env": "OPENROUTER_MODEL_PRO",
        "default_model": "openai/gpt-4o-mini",
        "default_model_pro": "openai/gpt-4o",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "key_envs": ("QWEN_API_KEY", "DASHSCOPE_API_KEY"),
        "model_env": "QWEN_MODEL",
        "model_pro_env": "QWEN_MODEL_PRO",
        "default_model": "qwen-plus",
        "default_model_pro": "qwen-max",
    },
}

SUPPORTED_PROVIDERS = ("gemini",) + tuple(OPENAI_COMPATIBLE_PROVIDERS)

_PY_TO_JSON_TYPE = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def resolve_provider() -> str:
    """Return the configured LLM provider name (default: ``gemini``)."""
    return (os.getenv("LLM_PROVIDER") or "gemini").strip().lower()


def _json_type(annotation) -> str:
    """Map a Python annotation to a JSON-schema type, defaulting to string."""
    return _PY_TO_JSON_TYPE.get(annotation, "string")


def build_openai_tools(tools):
    """Convert Python callables into (OpenAI tool schemas, name->callable map).

    Mirrors the callables that Gemini auto-calls: function name, docstring as
    description, and a JSON-schema object built from the signature. Variadic
    params (*args/**kwargs) are skipped; params without a default are required.
    """
    schemas = []
    tool_map = {}
    for func in tools:
        name = func.__name__
        tool_map[name] = func
        sig = inspect.signature(func)
        properties = {}
        required = []
        for pname, param in sig.parameters.items():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            annotation = param.annotation
            properties[pname] = {"type": _json_type(annotation)}
            if param.default is inspect.Parameter.empty:
                required.append(pname)
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": (inspect.getdoc(func) or "").strip()[:1024],
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return schemas, tool_map


class OpenAICompatibleProvider:
    """OpenAI-compatible chat provider (OpenAI / OpenRouter / Qwen).

    Supports plain-text chat and tool/function calling via a manual loop.
    """

    def __init__(self, name: str):
        if name not in OPENAI_COMPATIBLE_PROVIDERS:
            raise LLMConfigError(f"Unknown OpenAI-compatible provider: {name}")

        self.name = name
        self._spec = OPENAI_COMPATIBLE_PROVIDERS[name]
        self._client = None
        self._messages: list[dict] = []
        self._tool_schemas = None
        self._tool_map: dict = {}
        self.system_instruction = None
        self.active_model = None
        self._max_iterations = settings.tool_loop.max_iterations

        self.api_key = self._resolve_key()
        if not self.api_key:
            raise LLMConfigError(
                f"No API key for provider '{name}'. Set one of: "
                f"{', '.join(self._spec['key_envs'])}"
            )
        self.base_url = self._spec["base_url"]
        self.model_free = os.getenv(self._spec["model_env"], self._spec["default_model"])
        self.model_pro = os.getenv(self._spec["model_pro_env"], self._spec["default_model_pro"])

    def _resolve_key(self):
        for env in self._spec["key_envs"]:
            val = config.get_secret(env)
            if val:
                return val
        return None

    def _ensure_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise LLMConfigError("openai SDK not installed. Run: pip install openai")
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
            logger.info(
                "OpenAI-compatible provider initialised: name=%s, base_url=%s",
                self.name,
                self.base_url or "(sdk default)",
            )
        return self._client

    def create_session(self, system_instruction=None, tools=None, use_pro=False):
        """Prepare a chat session, optionally registering tools."""
        self.system_instruction = system_instruction
        self.active_model = self.model_pro if use_pro else self.model_free
        self._messages = []
        if system_instruction:
            self._messages.append({"role": "system", "content": system_instruction})
        if tools:
            self._tool_schemas, self._tool_map = build_openai_tools(tools)
        else:
            self._tool_schemas, self._tool_map = None, {}

    def chat(self, message, tools=None, use_pro=False):
        """Send a message and return the assistant text.

        Runs the tool-calling loop when tools are registered (via this call or
        a prior create_session); otherwise does a plain-text completion.
        """
        if self.active_model is None:
            self.create_session(self.system_instruction, tools=tools, use_pro=use_pro)
        elif tools is not None:
            self._tool_schemas, self._tool_map = build_openai_tools(tools)

        client = self._ensure_client()
        self._messages.append({"role": "user", "content": message})

        if self._tool_schemas:
            return self._run_tool_loop(client)
        return self._complete_text(client)

    def _complete_text(self, client):
        response = client.chat.completions.create(
            model=self.active_model,
            messages=self._messages,
        )
        text = response.choices[0].message.content if response.choices else None
        if text:
            self._messages.append({"role": "assistant", "content": text})
        return text

    def _run_tool_loop(self, client):
        for iteration in range(self._max_iterations):
            response = client.chat.completions.create(
                model=self.active_model,
                messages=self._messages,
                tools=self._tool_schemas,
                tool_choice="auto",
            )
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None)

            assistant_entry = {"role": "assistant", "content": message.content or ""}
            if tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ]
            self._messages.append(assistant_entry)

            if not tool_calls:
                return message.content

            for call in tool_calls:
                result = self._execute_tool_call(call)
                self._messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result}
                )
            logger.debug("Tool loop iteration %d: %d calls", iteration + 1, len(tool_calls))

        logger.warning("OpenAI tool loop reached max iterations (%d)", self._max_iterations)
        # One final pass without tools to extract a closing summary.
        final = client.chat.completions.create(
            model=self.active_model,
            messages=self._messages,
        )
        return final.choices[0].message.content

    def _execute_tool_call(self, call):
        name = call.function.name
        func = self._tool_map.get(name)
        if func is None:
            return f"Error: unknown tool '{name}'"
        try:
            arguments = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError as exc:
            return f"Error: invalid tool arguments JSON: {exc}"
        try:
            return str(func(**arguments))
        except Exception as exc:
            return f"Error: {exc}"

    def reset(self):
        """Reset the conversation, keeping the system instruction and tools."""
        self._messages = []
        if self.system_instruction:
            self._messages.append({"role": "system", "content": self.system_instruction})
