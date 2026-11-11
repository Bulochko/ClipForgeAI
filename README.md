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

The script downloads a pinned Windows x64 shared FFmpeg build from [FFmpeg-Builds](https://github.com/FFmpeg-Builds/FFmpeg-Builds), verifies its SHA-256 (including any cached archive used when offline), and checks the executable architecture, `-version`, `-buildconf`, and reported license before bundling. It refuses builds with `--enable-gpl` or `--enable-nonfree`, requires the expected LGPL-3.0-or-later license and the `mpeg4` encoder, and stages the shared DLLs alongside FFmpeg for PyInstaller. The official LGPL text is checked in at `licenses/COPYING.LGPLv3`, hash-verified during the build, and included in the portable distribution with generated `THIRD_PARTY_NOTICES.txt`.

To upgrade FFmpeg, update the pinned release tag, archive URL, and SHA-256 together in `build/build_windows.ps1`. Keep the LGPL shared variant and verify the new binary's license and configuration; the build intentionally fails if any check disagrees.

After FFmpeg validation, the script installs build dependencies into `.venv-build`, checks dependencies, and creates the PyInstaller folder. PyInstaller's DLL search is isolated from unrelated host tools so incompatible Qt/ICU libraries cannot leak into the package. The build validates packaged FFmpeg/FFprobe and rejects bundled host ICU DLLs before compiling the installer when Inno Setup is available. GitHub Actions also fails the smoke test if startup displays an exception dialog.

### Build with GitHub Actions

Open **Actions → Windows x64 build → Run workflow**. Successful runs publish the portable ZIP and installer as workflow artifacts. Pushing a tag such as `v0.3.0` also creates a GitHub Release with both files.

## Optional AI models — manual installation

AI model weights are intentionally excluded from both distributions.

1. Install Ollama manually from https://ollama.com/download/windows.
2. Run `INSTALL_AI.bat` to download `qwen3:4b`.
3. Open the AI Analyzer. The selected Whisper model is downloaded on first use.

The app includes the faster-whisper runtime in the full build. CUDA acceleration depends on compatible NVIDIA driver/CUDA/cuDNN runtime libraries; if unavailable, the transcription engine falls back to CPU INT8. Ollama is optional; without it, the app uses a basic speech-window heuristic.

The default workspace is `%USERPROFILE%\Videos\ClipForge AI`. If Windows denies access to that folder, the app creates its Projects and Exports folders under `%LOCALAPPDATA%\ClipForge AI` instead.

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
