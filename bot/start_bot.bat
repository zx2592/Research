@echo off
REM ============================================
REM V2 Research Telegram Bot - Background Launcher
REM ============================================
cd /d "%~dp0"
echo [%date% %time%] Starting V2 Telegram Bot... >> bot_log.txt
start /B pythonw telegram_bot.py
echo Bot started in background.
echo Logs: bot_service.log
echo To stop: run stop_bot.bat
