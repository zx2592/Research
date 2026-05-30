@echo off
REM ============================================
REM V2 Research Telegram Bot - Stop Script
REM ============================================
echo Stopping Telegram Bot...
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq telegram_bot*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq telegram_bot*" 2>nul
echo Done. Check Task Manager if bot is still running.
