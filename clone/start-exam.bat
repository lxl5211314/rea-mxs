@echo off
rem ---------------------------------------------------------------
rem  msx-clone launcher (written exam)
rem  MODE=exam: screenshot -> vision model -> answer. No audio, no ASR.
rem  First run asks for language + code mode; re-run setup:
rem      start-exam.bat setup
rem  Keep this file ASCII-only (cmd.exe misparses UTF-8 .bat files).
rem ---------------------------------------------------------------
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem suppress "python.exe has stopped working" / WER dialogs (a popup would be
rem visible in a shared screen). Process still crashes, run.log still records.
reg add "HKCU\Software\Microsoft\Windows\Windows Error Reporting" /v DontShowUI /t REG_DWORD /d 1 /f >nul 2>nul
rem and silence toast notifications for the exam session (any app's popup would
rem show up in a full-screen share). stop-exam.bat turns them back on.
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings" /v NOC_GLOBAL_SETTING_TOASTS_ENABLED /t REG_DWORD /d 0 /f >nul 2>nul

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set MODE=exam

set "PY=python"
where python >nul 2>nul || set "PY=E:\python3.10.4\python.exe"

if not exist ".env" (
    echo [warn] .env not found, copying from .env.example ...
    copy /y ".env.example" ".env" >nul
)

if /i "%~1"=="setup" goto setup
if /i "%~1"=="plain" goto run
if /i "%~1"=="guard" goto guard
findstr /b /c:"EXAM_LANG=" ".env" >nul 2>nul || goto setup
rem default: run under guardian so a mid-session crash comes back by itself
goto guard

:setup
echo ============================================================
echo  Written exam setup: pick language and code mode
echo ============================================================
"%PY%" exam_setup.py
echo.

:run
echo ============================================================
echo  msx-clone starting (exam mode, ready in ~3s)
echo  LLM : relay deepseek-v4.1-flash (thinking off, keep-warm)
echo  Shot: Shift+double-click full / Alt+double-click window
echo        Ctrl+Shift+S region / Shift+Alt+double-click twice = long
echo  Keys: F8 show/hide  F9 click-through  Ctrl+Shift+/ help
echo        Ctrl+Shift+Q twice = quit
echo        start-exam.bat setup = change language / code mode
echo        start-exam.bat plain = run once (no auto-restart)
echo        start-exam.bat guard = force guardian (default anyway)
echo ============================================================
echo.

"%PY%" mvp.py
set "RC=%errorlevel%"
goto done

:guard
echo ============================================================
echo  msx-clone under guardian (auto-restart on crash)
echo  a native crash (0xC000041D) restarts the UI in ~2s
echo  GUARDIAN_MAX=0 means unlimited; Ctrl+C stops it.
echo ============================================================
echo.
"%PY%" guardian.py
set "RC=%errorlevel%"

:done
echo.
if not "%RC%"=="0" (
    rem console was hidden by mvp.py; bring it back so the error is visible
    "%PY%" console.py show >nul 2>nul
    echo [msx-clone] exited with code %RC%
    echo ---- run.log tail ----
    powershell -NoProfile -Command "Get-Content -Encoding UTF8 -Tail 12 '%~dp0run.log'"
    pause
) else (
    rem normal exit: console stays hidden, just close
    exit /b 0
)
