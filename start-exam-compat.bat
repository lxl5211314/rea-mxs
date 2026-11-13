@echo off
rem Root launcher: written exam, compat mode (see clone\start-exam-compat.bat).
chcp 65001 >nul
cd /d "%~dp0clone"
call "%~dp0clone\start-exam-compat.bat" %*
