# ClipForge AI Desktop

Windows desktop application for local AI-assisted video clipping and vertical Shorts rendering.

## Version

0.2.0 (development build)

## Contents

- `app/main.py` — desktop UI and video workflow
- `app/ai_engine.py` — local Whisper/Ollama analysis integration
- `requirements.txt` — Python dependencies
- `START_CLIPFORGE.bat` — application launcher
- `INSTALL_AI.bat` — optional AI components setup
- `AI_MODELS.md` — local model recommendations

## Requirements

- Windows 10/11
- Python 3.11 or 3.12
- FFmpeg available on PATH
- Optional: Ollama for local LLM analysis

## Run

Run `START_CLIPFORGE.bat`. For AI setup, run `INSTALL_AI.bat` and follow `AI_MODELS.md`.

## Status

Development build. Validate on the target Windows machine before production use. Some GPU acceleration depends on compatible CUDA/cuDNN libraries.
