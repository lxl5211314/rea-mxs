@echo off
rem Root launcher: interview mode (listen to meeting audio).
rem Only two entry points on purpose: start.bat (interview) / start-exam.bat (exam).
chcp 65001 >nul
cd /d "%~dp0clone"
call "%~dp0clone\start.bat"
