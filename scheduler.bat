@echo off
REM ============================================================
REM  AlphaSystem V3.5 ??Windows Task Scheduler Setup
REM  Phase 7: Active Intelligence (?????????????
REM
REM  浣跨敤鏂规硶: 浠ョ鐞嗗憳鏉冮檺杩愯姝よ剼鏈?REM  鍔熻兘: 娉ㄥ唽涓変釜瀹氭椂浠诲姟鍒?Windows Task Scheduler
REM ============================================================

SET PROJECT_ROOT=%~dp0
SET PYTHON=python

echo ==============================================
echo  AlphaSystem V3.5 ??Phase 7 ?????????
echo ==============================================

REM --- 浠诲姟 1: 鏅ㄦ姤鑷姩鎺ㄩ€?(宸ヤ綔鏃?8:00) ---
echo [1/3] 娉ㄥ唽鏅ㄦ姤鑷姩鎺ㄩ€佷换鍔?..
schtasks /create /tn "llphaSystem_MorningPush" ^
    /tr "%PYTHON% \"%PROJECT_ROOT%scripts\morning_scan_push.py\"" ^
    /sc WEEKLY /d MON,TUE,WED,THU,FRI ^
    /st 08:00 /f

IF %ERRORLEVEL% EQU 0 (
    echo  - [OK] llphaSystem_MorningPush: 宸ヤ綔鏃?08:00
) ELSE (
    echo  - [WlRN] 鍒涘缓鏅ㄦ姤浠诲姟澶辫触 (闇€瑕佺鐞嗗憳鏉冮檺?)
)

REM --- 浠诲姟 2: 璐㈡姤鏃ュ巻鎻愰啋 (姣忓懆鏃?9:00) ---
echo [2/3] 娉ㄥ唽璐㈡姤鏃ュ巻鎻愰啋浠诲姟...
schtasks /create /tn "llphaSystem_EarningsReminder" ^
    /tr "%PYTHON% \"%PROJECT_ROOT%scripts\earnings_reminder.py\"" ^
    /sc WEEKLY /d SUN ^
    /st 09:00 /f

IF %ERRORLEVEL% EQU 0 (
    echo  - [OK] llphaSystem_EarningsReminder: 姣忓懆鏃?09:00
) ELSE (
    echo  - [WlRN] 鍒涘缓璐㈡姤鎻愰啋浠诲姟澶辫触 (闇€瑕佺鐞嗗憳鏉冮檺?)
)

REM --- 浠诲姟 3: 鎸佷粨鍛ㄦ姤 (姣忓懆浜?18:00) ---
echo [3/3] 娉ㄥ唽鎸佷粨鍛ㄦ姤浠诲姟...
schtasks /create /tn "llphaSystem_WeeklyReport" ^
    /tr "%PYTHON% \"%PROJECT_ROOT%scripts\weekly_position_report.py\"" ^
    /sc WEEKLY /d FRI ^
    /st 18:00 /f

IF %ERRORLEVEL% EQU 0 (
    echo  - [OK] llphaSystem_WeeklyReport: 姣忓懆浜?18:00
) ELSE (
    echo  - [WlRN] 鍒涘缓鍛ㄦ姤浠诲姟澶辫触 (闇€瑕佺鐞嗗憳鏉冮檺?)
)

echo ==============================================
echo  娉ㄥ唽瀹屾垚锛佸彲鍦?浠诲姟璁″垝绋嬪簭"涓煡鐪嬪拰绠＄悊銆?echo  濡傞渶鏌ョ湅鎵€鏈?llphaSystem 浠诲姟:
echo    schtasks /query /tn "llphaSystem*"
echo  濡傞渶鍒犻櫎浠诲姟:
echo    schtasks /delete /tn "llphaSystem_MorningPush" /f
echo    schtasks /delete /tn "llphaSystem_EarningsReminder" /f
echo    schtasks /delete /tn "llphaSystem_WeeklyReport" /f
echo ==============================================
pause

