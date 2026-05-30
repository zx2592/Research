import logging
import asyncio
from telegram import Bot

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, config):
        self.config = config
        self.token = config['telegram'].get('bot_token')
        self.chat_id = config['telegram'].get('chat_id')
        self.bot = None
        
        if self.token and self.token != "YOUR_TELEGRAM_BOT_TOKEN_HERE":
            try:
                self.bot = Bot(token=self.token)
            except Exception as e:
                logger.error(f"Failed to initialize Telegram Bot: {e}")

    async def send_alert(self, item):
        """
        Send formatted alert.
        """
        if not self.bot or not self.chat_id:
            logger.warning("Telegram Bot not configured, skipping alert.")
            return

        score = item.get('score', 0)
        emoji = "🔴" if score >= 9 else "🟠" if score >= 7 else "🔵"
        
        message = f"""
{emoji} **Investment Alert** (Score: {score}/10)

**{item.get('title')}**

Detected at: {item.get('published', 'N/A')}
Source: {item.get('source')}

**Summary**:
{item.get('summary')}

**Analysis**:
{item.get('reasoning')}

[Read Original]({item.get('link')})
"""
        
        try:
            # Telegram limits msg length to 4096 chars
            if len(message) > 4000:
                message = message[:4000] + "..."
                
            await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='Markdown')
            logger.info(f"Sent Telegram alert for: {item.get('title')}")
            
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def send_sync(self, item):
        """
        Wrapper to run async send in sync context if needed.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        loop.run_until_complete(self.send_alert(item))
