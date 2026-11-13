@echo off
rem ---------------------------------------------------------------
rem  msx-clone launcher (compat)
rem  For machines where the normal launcher dies with code
rem  -1073740771 (0xC000041D = STATUS_FATAL_USER_CALLBACK_EXCEPTION).
rem  Turns off the two native touch points that run on a timer:
rem    STEALTH_KEEPALIVE=0  -> no 5s WDA/TOPMOST refresh loop
rem    CLOAK_CONSOLE=0      -> console keeps its own capture affinity
rem  The answer window still gets WDA_EXCLUDEFROMCAPTURE once at
rem  startup, so screenshots / screen sharing still miss it.
rem ---------------------------------------------------------------
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set MODE=exam
set STEALTH_KEEPALIVE=0
set CLOAK_CONSOLE=0

set "PY=python"
where python >nul 2>nul || set "PY=E:\python3.10.4\python.exe"

if not exist ".env" copy /y ".env.example" ".env" >nul

echo ============================================================
echo  msx-clone starting (exam / COMPAT mode)
echo  stealth keepalive = off   console WDA = off
echo  Shot: Shift+double-click full / Alt+double-click window
echo        Ctrl+Shift+S region / Shift+Alt+double-click twice = long
echo  Keys: F8 show/hide  F9 click-through  Ctrl+Shift+/ help
echo        Ctrl+Shift+Q twice = quit
echo ============================================================
echo.

"%PY%" mvp.py
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" (
    echo [msx-clone] exited with code %RC%
    echo ---- run.log tail ----
    powershell -NoProfile -Command "Get-Content -Encoding UTF8 -Tail 12 '%~dp0run.log'"
) else (
    echo [msx-clone] exited
)
pause
