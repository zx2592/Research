import logging
import yaml
import asyncio
import os
import sys

# Ensure we can import from local directories
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from notifiers.telegram_bot import TelegramNotifier
from notifiers.email_sender import EmailNotifier

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestNotification")

def load_config():
    with open('d:/AI/Auto/system/config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def run_test():
    logger.info("Starting Notification Test...")
    config = load_config()
    
    # 1. Telegram
    logger.info("Initializing Telegram...")
    tg = TelegramNotifier(config)
    
    # 2. Email
    logger.info("Initializing Email...")
    email = EmailNotifier(config)
    
    # Message content
    # We construct a fake 'item' to fit the existing send_alert interface
    test_message = "以后请多多指教！"
    
    item = {
        'title': "系统测试消息 (System Test)",
        'score': 10, # Give it a high score to ensure it looks important
        'summary': test_message,
        'reasoning': "用户请求测试发送机制 (User requested notification test).",
        'source': "System Admin",
        'published': "Now",
        'link': "http://localhost"
    }
    
    # Send Telegram
    logger.info("Sending Telegram message...")
    try:
        tg.send_sync(item)
        logger.info("Telegram sent.")
    except Exception as e:
        logger.error(f"Telegram failed: {e}")

    # Send Email
    logger.info("Sending Email...")
    try:
        email.send_alert(item)
        logger.info("Email sent.")
    except Exception as e:
        logger.error(f"Email failed: {e}")

    logger.info("Done.")

if __name__ == "__main__":
    run_test()
