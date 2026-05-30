#!/usr/bin/env python3
"""
Notifier - Telegram 推送通知
"""

import logging
import os
import requests
from dotenv import load_dotenv

from core import settings

load_dotenv()

logger = logging.getLogger(__name__)


def send_telegram_message(message):
    """
    Sends a message via Telegram Bot API.
    自动分段处理长消息（Telegram 限制 4096 字符）。
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.warning("Telegram credentials not found.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    MAX_LEN = settings.bot.max_message_length

    # 分段
    chunks = []
    text = message or "⚠️ 空消息"
    while text:
        if len(text) <= MAX_LEN:
            chunks.append(text)
            break
        split_pos = text.rfind('\n', 0, MAX_LEN)
        if split_pos == -1 or split_pos < MAX_LEN // 2:
            split_pos = MAX_LEN
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip('\n')

    success = True
    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            if not response.ok:
                # Markdown 解析失败，回退纯文本
                payload.pop("parse_mode", None)
                requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error("Telegram send failed: %s", e)
            success = False

    return success


if __name__ == "__main__":
    send_telegram_message("🧪 V3.0 Research System - Test Message")
