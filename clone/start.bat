@echo off
rem ---------------------------------------------------------------
rem  msx-clone launcher (Windows)
rem  LLM: local relay "yonyou" -> deepseek-v4.1-flash (thinking off + keep-warm)
rem  ASR: local faster-whisper-base @ CUDA
rem  NOTE: keep this file ASCII-only. cmd.exe misparses UTF-8 .bat files.
rem  Chinese docs: ..\docs\ (see the .md files, open in a UTF-8 editor)
rem ---------------------------------------------------------------
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
rem interview mode: listen to the meeting audio. Use start-exam.bat for written tests.
set MODE=interview

set "PY=python"
where python >nul 2>nul || set "PY=E:\python3.10.4\python.exe"

if not exist ".env" (
    echo [warn] .env not found, copying from .env.example ...
    copy /y ".env.example" ".env" >nul
)

echo ============================================================
echo  msx-clone starting (loading ASR + warming LLM, ~20s)
echo  LLM : relay deepseek-v4.1-flash (thinking off, keep-warm)
echo  ASR : local faster-whisper-base @ CUDA
echo  Keys: F8 show/hide  F9 click-through  Ctrl+Shift+/ help
echo        Ctrl+Shift+Q twice = quit
echo ============================================================
echo.

"%PY%" mvp.py
set "RC=%errorlevel%"

echo.
if not "%RC%"=="0" (
    echo [msx-clone] exited with code %RC%
) else (
    echo [msx-clone] exited
)
pause
