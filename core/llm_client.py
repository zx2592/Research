#!/usr/bin/env python3
"""
Unified LLM client for desktop and VPS modes.

Desktop mode delegates model execution to IDE providers (Claude Code, Codex,
Gemini ADC) with automatic fallback to Gemini API if available.
VPS mode talks to Gemini via google-genai.
"""

import logging
import os
import shutil
import sys

from core import config  # noqa: F401 - ensures load_dotenv runs once

logger = logging.getLogger(__name__)


class LLMConfigError(Exception):
    """Raised when LLM client configuration is invalid or missing."""


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class LLMClient:
    """Unified LLM interface supporting desktop and VPS execution."""

    def __init__(self, force_mode=None):
        self.mode = force_mode or self._detect_mode()
        self.client = None
        self.client_active = None
        self.chat_session = None
        self.system_instruction = None
        self.active_api_label = None
        self.active_model = None
        self._chat_tools = None

        if self.mode == "vps":
            self._init_vps()
        elif self.mode == "desktop":
            self._init_desktop()

    def _detect_mode(self):
        """Auto-detect execution mode.

        Priority:
        1. LLM_MODE explicitly set to "desktop" or "vps" → use it
        2. RUNNING_AS_BOT / RUNNING_AS_SENTINEL → vps
        3. IDE CLI available (claude/codex on PATH) → desktop
        4. Windows platform (no service markers) → desktop
        5. Has GEMINI_API_KEY (non-Windows, no IDE CLI) → vps
        6. Default → desktop
        """
        env_mode = os.getenv("LLM_MODE", "auto")
        if env_mode in ("desktop", "vps"):
            return env_mode

        if os.getenv("RUNNING_AS_BOT") or os.getenv("RUNNING_AS_SENTINEL"):
            return "vps"

        if shutil.which("claude") or shutil.which("codex"):
            return "desktop"

        if sys.platform == "win32":
            return "desktop"

        if os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_BACKUP"):
            return "vps"

        return "desktop"

    # ------------------------------------------------------------------
    # VPS mode initialisation
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
    # Desktop mode initialisation
    # ------------------------------------------------------------------

    def _init_desktop(self):
        """Initialize desktop mode — detect IDE provider and prepare fallback."""
        from core.ide_providers import detect_provider

        self._ide_provider = detect_provider()
        self._desktop_tools = None

        # Prepare Gemini API fallback (lazy — only init on actual failure)
        self._vps_fallback_ready = bool(
            os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_BACKUP")
        )

        if self._ide_provider:
            logger.info("Desktop mode: IDE provider=%s, fallback=%s",
                        self._ide_provider.name,
                        "ready" if self._vps_fallback_ready else "none")
        else:
            logger.info("Desktop mode: no IDE provider detected, fallback=%s",
                        "ready" if self._vps_fallback_ready else "none")

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
    # create_chat — dispatch by mode
    # ------------------------------------------------------------------

    def create_chat(self, tools=None, use_pro=False, preferred_label=None):
        """Create a fresh chat session."""
        if self.mode == "vps":
            return self._create_chat_vps(tools, use_pro, preferred_label)
        if self.mode == "desktop":
            return self._create_chat_desktop(tools, use_pro)
        logger.warning("create_chat: unknown mode '%s'", self.mode)

    def _create_chat_vps(self, tools, use_pro, preferred_label):
        """Create a VPS-mode chat session via Gemini API."""
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

    def _create_chat_desktop(self, tools, use_pro):
        """Create a desktop-mode chat session via IDE provider."""
        self._desktop_tools = tools
        if self._ide_provider:
            try:
                self._ide_provider.create_session(
                    system_instruction=self.system_instruction,
                    tools=tools,
                    use_pro=use_pro,
                )
                logger.info(
                    "Desktop session: provider=%s, tools=%d, pro=%s",
                    self._ide_provider.name,
                    len(tools) if tools else 0,
                    use_pro,
                )
                return
            except Exception as exc:
                logger.warning("IDE provider %s init failed: %s", self._ide_provider.name, exc)
        # IDE not available or failed — fallback deferred to chat()

    # ------------------------------------------------------------------
    # chat — dispatch by mode
    # ------------------------------------------------------------------

    def chat(self, message, tools=None, use_pro=False):
        """Send a message and return text output."""
        if self.mode == "vps":
            return self._chat_vps(message, tools, use_pro)
        if self.mode == "desktop":
            return self._chat_desktop(message, tools, use_pro)
        return f"[Error: Unknown mode '{self.mode}']"

    def _chat_vps(self, message, tools, use_pro):
        """Send a message via Gemini API (VPS mode)."""
        if not self.chat_session:
            try:
                self._create_chat_vps(tools=tools, use_pro=use_pro, preferred_label=None)
            except Exception as exc:
                return f"Error: {str(exc)}"

        try:
            result_text = self._send_message_once(message)
            return result_text or "⚠️ Agent 完成了任务但没有返回文本响应。"
        except Exception as exc:
            if self.active_api_label == "primary" and self.api_key_backup:
                logger.warning("Primary Gemini key failed, retrying with backup key: %s", exc)
                try:
                    self._create_chat_vps(
                        tools=tools if tools is not None else self._chat_tools,
                        use_pro=use_pro,
                        preferred_label="backup",
                    )
                    result_text = self._send_message_once(message)
                    return result_text or "⚠️ Agent 完成了任务但没有返回文本响应。"
                except Exception as backup_exc:
                    return f"Error: primary key failed ({exc}); backup key failed ({backup_exc})"

            return f"Error: {str(exc)}"

    def _chat_desktop(self, message, tools, use_pro):
        """Send a message via IDE provider, with Gemini API fallback."""
        # 1) Try IDE provider
        if self._ide_provider:
            try:
                result = self._ide_provider.send_message(message)
                if result:
                    return result
            except Exception as exc:
                logger.warning("IDE provider failed: %s, falling back to Gemini API", exc)

        # 2) Fallback: Gemini API (lazy init VPS components)
        if self._vps_fallback_ready:
            if not hasattr(self, "api_key"):
                try:
                    self._init_vps()
                except LLMConfigError as exc:
                    return f"[Error: IDE provider unavailable; Gemini fallback failed: {exc}]"

            self.chat_session = None
            effective_tools = tools or self._desktop_tools
            try:
                self._create_chat_vps(effective_tools, use_pro, None)
                return self._chat_vps(message, tools, use_pro)
            except Exception as exc:
                return f"Error: IDE provider failed; Gemini fallback also failed: {exc}"

        return "[Error: No IDE provider available and no Gemini API key for fallback]"

    # ------------------------------------------------------------------
    # Internal helpers (VPS)
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
        if self.mode == "desktop" and hasattr(self, "_ide_provider") and self._ide_provider:
            self._ide_provider.reset()
