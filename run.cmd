@echo off
setlocal EnableExtensions
rem Launch Lyra AI with the Node runtime bundled inside DeepSeek Harness.

set "APP_DIR=%LOCALAPPDATA%\Programs\DeepSeek Harness"
if defined DSH_APP_DIR set "APP_DIR=%DSH_APP_DIR%"

rem Keep the launcher and the agent module pointed at the same installation.
if not defined DSH_APP_EXE set "DSH_APP_EXE=%APP_DIR%\DeepSeek Harness.exe"
if not defined DSH_CLI_JS set "DSH_CLI_JS=%APP_DIR%\resources\app.asar\dsh\node_modules\@deepseek-ai\dsh-desktop-host\lib\cli.js"
if not defined DSH_CLI set "DSH_CLI=%APP_DIR%\resources\runtime\cli\bin\dsh.cmd"

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
