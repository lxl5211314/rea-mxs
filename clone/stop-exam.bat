@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo  msx-clone  STOP  -  close every running instance
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$list = Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'guardian\.py|mvp\.py') -or ($_.Name -eq 'cmd.exe' -and $_.CommandLine -match 'start-exam\.bat') }; if (-not $list) { Write-Host '[stop] nothing running'; exit 0 }; $list | Sort-Object { if ($_.CommandLine -match 'guardian') { 0 } elseif ($_.Name -eq 'cmd.exe') { 2 } else { 1 } } | ForEach-Object { Write-Host ('[stop] kill {0} pid={1}' -f $_.Name, $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

ping -n 3 127.0.0.1 >nul

rem restore toast notifications that start-exam.bat switched off for the session
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings" /v NOC_GLOBAL_SETTING_TOASTS_ENABLED /t REG_DWORD /d 1 /f >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$n = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'mvp\.py|guardian\.py' }).Count; if ($n -eq 0) { Write-Host '[stop] done - no msx-clone process left' } else { Write-Host ('[stop] WARNING: ' + $n + ' still alive') }"

echo.
echo Tip: run start-exam.bat again any time.
pause
