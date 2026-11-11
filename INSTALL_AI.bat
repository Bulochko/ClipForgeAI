@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo =============================================
echo       ClipForge AI - Local AI components
echo =============================================
if not exist .venv\Scripts\activate.bat (
  echo Сначала запусти START_CLIPFORGE.bat, чтобы создать окружение.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install faster-whisper
if errorlevel 1 goto error
where ollama >nul 2>nul
if errorlevel 1 (
  echo.
  echo Ollama не найден.
  echo Установи его с https://ollama.com/download/windows
  echo Затем снова запусти INSTALL_AI.bat для загрузки модели.
  start https://ollama.com/download/windows
  pause
  exit /b 0
)
echo.
echo Загружаем Qwen3 4B для локального анализа транскрипта...
ollama pull qwen3:4b
if errorlevel 1 goto error
echo.
echo AI-компоненты установлены. Перезапусти ClipForge AI.
pause
exit /b 0
:error
echo Не удалось установить один из компонентов. Проверь сообщения выше.
pause
exit /b 1
