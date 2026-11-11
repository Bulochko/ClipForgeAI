@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo =============================================
echo       ClipForge AI - Optional AI setup
echo =============================================
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama is not installed. It is optional and is not bundled with ClipForge AI.
  echo Install it manually from https://ollama.com/download/windows
  start https://ollama.com/download/windows
  echo After installation, run this file again.
  pause
  exit /b 0
)
echo.
echo Downloading the Qwen3 4B language model for local transcript scoring...
ollama pull qwen3:4b
if errorlevel 1 goto error
echo.
echo Qwen3 4B is ready.
echo Whisper speech-recognition weights are downloaded separately when you
echo select a Whisper model in the AI Analyzer and start the first analysis.
echo No model weights are included in the portable archive or installer.
pause
exit /b 0
:error
echo Model download failed. Check that Ollama is running and try again.
pause
exit /b 1
