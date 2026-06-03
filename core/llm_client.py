#!/usr/bin/env python3
"""
LLM client for API-driven (VPS) execution.

Talks to Gemini via google-genai with ordered primary/backup key retry.
"""

import logging
import os
import sys

from core import config  # noqa: F401 - ensures load_dotenv runs once

logger = logging.getLogger(__name__)


class LLMConfigError(Exception):
    """Raised when LLM client configuration is invalid or missing."""


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class LLMClient:
    """Gemini API client with primary/backup key routing."""

    def __init__(self):
        self.mode = "vps"
        self.client = None
        self.client_active = None
        self.chat_session = None
        self.system_instruction = None
        self.active_api_label = None
        self.active_model = None
        self._chat_tools = None
        self._oai = None

        # Provider selection: gemini (default, fully implemented) or a
        # reserved OpenAI-compatible provider (openai / openrouter / qwen).
        from core.llm_providers import resolve_provider

        self.provider = resolve_provider()
        if self.provider == "gemini":
            self._init_vps()
        else:
            self._init_openai_compatible()

    def _init_openai_compatible(self):
        """Initialise a reserved OpenAI-compatible provider."""
        from core.llm_providers import OpenAICompatibleProvider

        self._oai = OpenAICompatibleProvider(self.provider)
        self.model_free = self._oai.model_free
        self.model_pro = self._oai.model_pro
        logger.info("LLM provider=%s (OpenAI-compatible, reserved)", self.provider)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_vps(self):
        """Initialize Gemini SDK client handles."""
        try:
            from google import genai
            from google.genai import types

            self._genai = genai
            self._types = types
        except ImportError:
            raise LLMConfigError("google-genai not installed. Run: pip install google-genai")

        self.api_key = config.get_secret("GEMINI_API_KEY")
        self.api_key_backup = config.get_secret("GEMINI_API_KEY_BACKUP")

        if not self.api_key and not self.api_key_backup:
            raise LLMConfigError("No GEMINI_API_KEY found in .env")

        bootstrap_key = self.api_key or self.api_key_backup
        self.client = self._genai.Client(api_key=bootstrap_key, vertexai=False)
        self.client_active = self.client
        self.model_free = os.getenv("VPS_MODEL", "gemini-3-flash")
        self.model_pro = os.getenv("VPS_MODEL_PRO", "gemini-3.1-pro")

    def _iter_api_candidates(self, preferred_label=None):
        """Yield API keys in retry order: primary first, backup as fallback."""
        candidates = []
        if self.api_key:
            candidates.append(("primary", self.api_key))
        if self.api_key_backup:
            candidates.append(("backup", self.api_key_backup))

        if preferred_label is not None:
            candidates = [item for item in candidates if item[0] == preferred_label]

        return candidates

    # ------------------------------------------------------------------
    # Shared
    # ------------------------------------------------------------------

    def load_system_instruction(self, filepath):
        """Load a system instruction file if it exists."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                self.system_instruction = f.read()
        except FileNotFoundError:
            logger.warning("System instruction file not found: %s", filepath)

    # ------------------------------------------------------------------
    # create_chat
    # ------------------------------------------------------------------

    def create_chat(self, tools=None, use_pro=False, preferred_label=None):
        """Create a fresh chat session (Gemini API, or reserved provider)."""
        if self.provider != "gemini":
            self._oai.create_session(
                system_instruction=self.system_instruction,
                tools=tools,
                use_pro=use_pro,
            )
            self.active_model = self._oai.active_model
            return None

        model = self.model_pro if use_pro else self.model_free
        self._chat_tools = tools

        config_kwargs = {}
        if tools:
            config_kwargs["tools"] = tools
        if self.system_instruction:
            config_kwargs["system_instruction"] = self.system_instruction

        last_error = None
        for label, api_key in self._iter_api_candidates(preferred_label=preferred_label):
            try:
                client = self._genai.Client(api_key=api_key, vertexai=False)
                chat_session = client.chats.create(
                    model=model,
                    config=self._types.GenerateContentConfig(**config_kwargs),
                )
                self.client_active = client
                self.chat_session = chat_session
                self.active_api_label = label
                self.active_model = model
                logger.info(
                    "Chat created: model=%s, tools=%d, key=%s",
                    model,
                    len(tools) if tools else 0,
                    label,
                )
                return chat_session
            except Exception as exc:
                last_error = exc
                logger.warning("Failed to create chat with %s Gemini key: %s", label, exc)

        raise last_error or LLMConfigError("No Gemini API key available for chat creation")

    # ------------------------------------------------------------------
    # chat
    # ------------------------------------------------------------------

    def chat(self, message, tools=None, use_pro=False):
        """Send a message and return text output."""
        if self.provider != "gemini":
            try:
                result_text = self._oai.chat(message, tools=tools, use_pro=use_pro)
                return result_text or "⚠️ Agent 完成了任务但没有返回文本响应。"
            except Exception as exc:
                return f"Error: {str(exc)}"

        if not self.chat_session:
            try:
                self.create_chat(tools=tools, use_pro=use_pro, preferred_label=None)
            except Exception as exc:
                return f"Error: {str(exc)}"

        try:
            result_text = self._send_message_once(message)
            return result_text or "⚠️ Agent 完成了任务但没有返回文本响应。"
        except Exception as exc:
            if self.active_api_label == "primary" and self.api_key_backup:
                logger.warning("Primary Gemini key failed, retrying with backup key: %s", exc)
                try:
                    self.create_chat(
                        tools=tools if tools is not None else self._chat_tools,
                        use_pro=use_pro,
                        preferred_label="backup",
                    )
                    result_text = self._send_message_once(message)
                    return result_text or "⚠️ Agent 完成了任务但没有返回文本响应。"
                except Exception as backup_exc:
                    return f"Error: primary key failed ({exc}); backup key failed ({backup_exc})"

            return f"Error: {str(exc)}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parts_to_text(parts):
        """Join all text-bearing Gemini parts without touching response.text first."""
        if not parts:
            return None

        chunks = []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)

        return "".join(chunks) if chunks else None

    def _extract_response_text(self, response):
        """Normalize text extraction across Gemini response shapes."""
        result_text = None

        if hasattr(response, "parts") and response.parts:
            result_text = self._parts_to_text(response.parts)

        if result_text is None and hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None)
                result_text = self._parts_to_text(parts)
                if result_text:
                    break

        if result_text is None:
            try:
                result_text = response.text
            except Exception:
                result_text = None

        return result_text

    def _send_message_once(self, message):
        """Send one message through the current chat session."""
        response = self.chat_session.send_message(message)
        result_text = self._extract_response_text(response)

        if not result_text:
            followup = self.chat_session.send_message("请用中文简要总结一下刚才完成的任务和关键发现。")
            result_text = self._extract_response_text(followup)

        return result_text

    def reset(self):
        """Reset the current chat session."""
        self.chat_session = None
        if self.provider != "gemini" and self._oai is not None:
            self._oai.reset()
