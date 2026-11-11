param([string]$Python = "py", [switch]$SkipClean)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host "== ClipForge AI Windows x64 build ==" -ForegroundColor Cyan
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) { throw "Python launcher '$Python' was not found." }
$PythonArgs = @()
if ([System.IO.Path]::GetFileNameWithoutExtension($Python) -eq "py") { $PythonArgs = @("-3.11") }
& $Python @PythonArgs -c "import sys; assert sys.version_info[:2] == (3,11), sys.version"
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 is required." }
if (-not $SkipClean) { Remove-Item -Recurse -Force .build-temp, dist -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force tools | Out-Null
$FfmpegZip = Join-Path $env:TEMP "clipforge-ffmpeg-lgpl.zip"
$FfmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-lgpl.zip"
Write-Host "Downloading LGPL FFmpeg build..."
Invoke-WebRequest -Uri $FfmpegUrl -OutFile $FfmpegZip
$Extract = Join-Path $env:TEMP "clipforge-ffmpeg"
Remove-Item -Recurse -Force $Extract -ErrorAction SilentlyContinue
Expand-Archive -Path $FfmpegZip -DestinationPath $Extract -Force
$Ffmpeg = Get-ChildItem $Extract -Filter ffmpeg.exe -Recurse | Select-Object -First 1
$Ffprobe = Get-ChildItem $Extract -Filter ffprobe.exe -Recurse | Select-Object -First 1
if (-not $Ffmpeg -or -not $Ffprobe) { throw "FFmpeg archive missing executables." }
Copy-Item $Ffmpeg.FullName (Join-Path $Root "tools\ffmpeg.exe") -Force
Copy-Item $Ffprobe.FullName (Join-Path $Root "tools\ffprobe.exe") -Force
$License = & (Join-Path $Root "tools\ffmpeg.exe") -L 2>&1 | Out-String
if ($License -notmatch "LGPL") { throw "FFmpeg binary does not report LGPL. Refusing to bundle it." }
Set-Content -Path (Join-Path $Root "THIRD_PARTY_NOTICES.txt") -Value @"
ClipForge AI third-party components

FFmpeg: BtbN/FFmpeg-Builds LGPL variant.
License/build details: tools\ffmpeg.exe -L and -buildconf
Source: https://ffmpeg.org/
Build distribution: https://github.com/BtbN/FFmpeg-Builds

PySide6 / Qt, faster-whisper, CTranslate2 and PyAV are third-party components
under their respective licenses. Consult upstream license files.
"@ -Encoding UTF8
& $Python @PythonArgs -m venv .venv-build
$VenvPython = Join-Path $Root ".venv-build\Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }
$env:PATH = "$(Join-Path $Root 'tools');$env:PATH"
& $VenvPython build\check_dependencies.py
if ($LASTEXITCODE -ne 0) { throw "Dependency check failed." }
& $VenvPython -m PyInstaller --noconfirm --clean --workpath .build-temp clipforge.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
Copy-Item README.md, AI_MODELS.md, THIRD_PARTY_NOTICES.txt, INSTALL_AI.bat -Destination dist\ClipForgeAI\ -Force
Write-Host "Portable folder created: dist\ClipForgeAI" -ForegroundColor Green
$Iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $Iscc) {
    $Candidate = "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $Candidate) { $Iscc = Get-Item $Candidate }
}
if ($Iscc) {
    & $Iscc.Source installer\ClipForgeAI.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
} else { Write-Warning "Inno Setup 6 not found; installer skipped." }
