#!/usr/bin/env python3
"""
Research Telegram Bot Service Runner
Runs the bot with proper logging and restart capability.
"""

import os
import sys
import time
import logging
import subprocess
from datetime import datetime

# Setup
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

LOG_FILE = os.path.join(SCRIPT_DIR, "bot_service.log")
PID_FILE = os.path.join(SCRIPT_DIR, "bot.pid")
BOT_SCRIPT = os.path.join(SCRIPT_DIR, "telegram_bot.py")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def write_pid():
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def remove_pid():
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)


def run_bot():
    """Run the bot with auto-restart on crash."""
    write_pid()
    restart_count = 0
    max_restarts = 10
    restart_window = 3600
    restart_times = []

    logger.info("=" * 50)
    logger.info("V2 Research Telegram Bot Service Starting")
    logger.info("=" * 50)

    while True:
        try:
            logger.info(f"Starting telegram_bot.py (restart #{restart_count})")

            process = subprocess.Popen(
                [sys.executable, BOT_SCRIPT],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=SCRIPT_DIR,
                env={**os.environ, "PYTHONPATH": PROJECT_ROOT}
            )

            for line in process.stdout:
                line = line.strip()
                if line:
                    logger.info(f"[BOT] {line}")

            process.wait()
            exit_code = process.returncode
            logger.warning(f"Bot exited with code {exit_code}")

            now = time.time()
            restart_times = [t for t in restart_times if now - t < restart_window]
            restart_times.append(now)

            if len(restart_times) > max_restarts:
                logger.error(f"Too many restarts ({max_restarts}) in {restart_window}s. Stopping.")
                break

            restart_count += 1
            logger.info("Restarting in 5 seconds...")
            time.sleep(5)

        except KeyboardInterrupt:
            logger.info("Received shutdown signal. Stopping...")
            break
        except Exception as e:
            logger.error(f"Service error: {e}")
            time.sleep(10)

    remove_pid()
    logger.info("Service stopped.")


if __name__ == "__main__":
    run_bot()
