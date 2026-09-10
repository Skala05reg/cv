@echo off
setlocal
chcp 65001 >nul
where pwsh >nul 2>nul
if "%errorlevel%"=="0" (
  pwsh -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish.ps1" %*
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish.ps1" %*
)
exit /b %errorlevel%
