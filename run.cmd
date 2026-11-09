@echo off
setlocal EnableExtensions
rem Launch Lyra AI with the Node runtime bundled inside DeepSeek Harness.

set "APP_DIR=C:\Users\Korobka\AppData\Local\Programs\DeepSeek Harness"
if defined DSH_APP_DIR set "APP_DIR=%DSH_APP_DIR%"

set "DSH_VERSION="
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /c:"TELEGRAM_PROXY=" "%~dp0.env" 2^>nul`) do set "TELEGRAM_PROXY=%%B"
if defined TELEGRAM_PROXY (
  set "HTTP_PROXY=%TELEGRAM_PROXY%"
  set "HTTPS_PROXY=%TELEGRAM_PROXY%"
  set "NODE_USE_ENV_PROXY=1"
  echo [run] using proxy %TELEGRAM_PROXY%
)

set "PATH=%APP_DIR%\resources\runtime\bin;%PATH%"
set "ELECTRON_RUN_AS_NODE=1"

"%APP_DIR%\DeepSeek Harness.exe" --expose-internals "%~dp0src\bot.mjs"
exit /b %errorlevel%
