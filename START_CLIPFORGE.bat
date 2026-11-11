@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================
echo       ClipForge AI - Windows
echo ======================================
where py >nul 2>nul
if errorlevel 1 (
  echo Python не найден. Установи Python 3.11 или 3.12 с сайта python.org и включи Add Python to PATH.
  pause
  exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo FFmpeg не найден. Установи его командой: winget install Gyan.FFmpeg
  echo После установки закрой это окно и запусти START_CLIPFORGE.bat снова.
  pause
  exit /b 1
)
if not exist .venv (
  echo Создаём виртуальное окружение...
  py -3 -m venv .venv
  if errorlevel 1 goto error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto error
python app\main.py
if errorlevel 1 goto error
goto end
:error
echo Произошла ошибка. Проверь сообщения выше.
pause
:end
