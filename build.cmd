@echo off
setlocal
chcp 65001 >nul
if defined RESUME_PYTHON goto run
set "RESUME_PYTHON=C:\Users\yvnpl\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%RESUME_PYTHON%" goto run
set "RESUME_PYTHON=C:\Users\yvnpl\miniconda3\envs\kokoro\python.exe"
if exist "%RESUME_PYTHON%" goto run
set "RESUME_PYTHON=python"
:run
"%RESUME_PYTHON%" -X utf8 "%~dp0build.py" %*
set "RESUME_BUILD_EXIT=%errorlevel%"
if not "%RESUME_BUILD_EXIT%"=="0" echo Build failed. Read README.md for setup and editing instructions.
exit /b %RESUME_BUILD_EXIT%
