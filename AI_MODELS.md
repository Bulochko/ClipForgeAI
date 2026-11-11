# Local AI models for ClipForge AI on RTX 4060 8 GB

## Recommended profile

| Task | Component | Setting | Notes |
|---|---|---|---|
| Speech recognition | faster-whisper `small` | CUDA `int8_float16`, CPU `int8` fallback | Good balance of speed and quality |
| Higher-accuracy transcription | faster-whisper `medium` | Run separately from the LLM | Slower and more memory-intensive |
| Higher-quality transcription | faster-whisper `large-v3-turbo` | Check free VRAM first | Heavier workload |
| Clip selection | Ollama `qwen3:4b` | Context 4096 | Compact local model for transcript scoring and JSON output |
| Scene detection | PySceneDetect (planned) | CPU | No large neural model required |
| Video encoding | FFmpeg + NVENC (if available) | H.264 NVENC | NVIDIA hardware encoding |

## Why models run sequentially

The RTX 4060 has 8 GB VRAM. ClipForge first transcribes the video with Whisper, releases that model, and then sends the transcript to Ollama/Qwen3 4B. Avoid running multiple heavy AI tasks in parallel.

## Installation

1. Run `START_CLIPFORGE.bat` once.
2. Install Ollama for Windows: https://ollama.com/download/windows
3. Run `INSTALL_AI.bat` to install faster-whisper and download `qwen3:4b`.
4. Restart ClipForge AI and open the **AI Analyzer** tab.

Ollama's local API is available at `http://127.0.0.1:11434` by default.

## CUDA for Whisper

faster-whisper uses CTranslate2. For GPU mode, the project documentation describes NVIDIA cuBLAS for CUDA 12 and cuDNN 9 for CUDA 12. If these libraries are missing or incompatible, ClipForge falls back to CPU INT8. Do not install DLL files from unofficial archives.

Documentation: https://github.com/SYSTRAN/faster-whisper

## Disk space

Allow at least 8–12 GB free for Python dependencies and selected models. More space is needed if several Whisper models are installed.

## Current AI Analyzer limitations

- Clip selection is based on transcript text, not full visual understanding of every frame.
- If Ollama is unavailable, a speech-window heuristic is used.
- AI clip suggestions must be reviewed by a person before publication.
- Only process video that you own or are authorized to use.
