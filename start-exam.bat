@echo off
rem Root launcher: written exam (screenshot -> answer).
rem Pass "setup" once to change language / code mode: start-exam.bat setup
chcp 65001 >nul
cd /d "%~dp0clone"
call "%~dp0clone\start-exam.bat" %*
