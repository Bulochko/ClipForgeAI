# ClipForge AI Desktop

Local Windows desktop application for AI-assisted video clipping and vertical video exports.

## Current status

**Development build — not yet production-validated.** The current application can load a video, inspect it with FFprobe, render a selected time range through FFmpeg, and run transcript-based AI clip suggestions when optional AI components are installed. It is not yet a full nonlinear editor; scene understanding, subtitles, face tracking, batch editing and a full timeline remain future work.

## Windows distribution

The project provides a Windows x64 build pipeline:

- Portable distribution: `dist/ClipForgeAI-portable-win64.zip`
- Inno Setup installer: `dist/installer/ClipForgeAI-Setup-0.3.0-x64.exe`
- PyInstaller one-folder build: `clipforge.spec`
- Build script: `build/build_windows.ps1`
- Dependency checker: `build/check_dependencies.py`
- CI: `.github/workflows/windows-build.yml`

### Build locally (Windows 10/11 x64)

1. Install Python 3.11 x64.
2. Install Inno Setup 6 if you also want the installer.
3. Open PowerShell in the repository root.
4. Run:

   ```powershell
   .\build\build_windows.ps1
   ```

The script downloads the LGPL FFmpeg build, installs build dependencies into `.venv-build`, checks dependencies, creates the PyInstaller folder and compiles the installer when Inno Setup is available.

### Build with GitHub Actions

Open **Actions → Windows x64 build → Run workflow**. Successful runs publish the portable ZIP and installer as workflow artifacts. Pushing a tag such as `v0.3.0` also creates a GitHub Release with both files.

## Optional AI models — manual installation

AI model weights are intentionally excluded from both distributions.

1. Install Ollama manually from https://ollama.com/download/windows.
2. Run `INSTALL_AI.bat` to download `qwen3:4b`.
3. Open the AI Analyzer. The selected Whisper model is downloaded on first use.

The app includes the faster-whisper runtime in the full build. CUDA acceleration depends on compatible NVIDIA driver/CUDA/cuDNN runtime libraries; if unavailable, the transcription engine falls back to CPU INT8. Ollama is optional; without it, the app uses a basic speech-window heuristic.

## Technical requirements

- Windows 10/11 x64
- Python 3.11 x64 only for building from source; not required by end users
- FFmpeg and FFprobe are bundled in the Windows distribution
- Optional Ollama installation and separately downloaded model weights
- NVIDIA driver for optional CUDA acceleration

## Project layout

- `app/main.py` — PySide6 desktop UI and video workflow
- `app/ai_engine.py` — faster-whisper / Ollama integration
- `requirements.txt` — application UI dependencies
- `requirements-build.txt` — full build dependencies
- `clipforge.spec` — PyInstaller spec
- `installer/ClipForgeAI.iss` — Inno Setup definition
- `build/` — Windows build and dependency-check scripts

## Legal / media use

FFmpeg is bundled from the LGPL build variant. Build details and notices are generated into `THIRD_PARTY_NOTICES.txt`. Always verify the exact binary's license/build configuration before redistributing. Only process video that you own or are authorized to use.
