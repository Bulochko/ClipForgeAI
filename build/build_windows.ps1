param([string]$Python = "py", [switch]$SkipClean)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

trap {
    $Message = $_.Exception.Message
    if ($Message) { Write-Host "::error title=ClipForge Windows x64 build::$Message" }
    exit 1
}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host "== ClipForge AI Windows x64 build ==" -ForegroundColor Cyan

# Pin a specific FFmpeg-Builds Windows x64 LGPL shared release. Update the URL
# and SHA-256 together when intentionally upgrading FFmpeg.
$FfmpegArchiveName = "ffmpeg-N-128790-g9bee1e603c-win64-lgpl-shared.zip"
$FfmpegReleaseTag = "autobuild-2026-11-11-12-39"
$FfmpegUrl = "https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/$FfmpegReleaseTag/$FfmpegArchiveName"
$FfmpegSha256 = "f9d002b1da11eb579ecfb1bade24b3ecc53cd2e7715434c9a3591868dc515471"
$FfmpegLicense = "LGPL-3.0-or-later"
$FfmpegLicenseUrl = "https://www.gnu.org/licenses/lgpl-3.0.txt"

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $Output = & $Executable @Arguments 2>&1 | Out-String
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -ne 0) {
        $Details = $Output.Trim()
        throw "$Description failed with exit code $ExitCode. Output: $Details"
    }
    return $Output
}

function Get-PeMachine {
    param([Parameter(Mandatory = $true)][string]$Path)

    $Stream = $null
    $Reader = $null
    try {
        $Stream = [System.IO.File]::OpenRead($Path)
        $Reader = [System.IO.BinaryReader]::new($Stream)
        if ($Stream.Length -lt 64) { throw "Executable is too small to be a valid PE file: $Path" }
        [void]$Stream.Seek(0x3C, [System.IO.SeekOrigin]::Begin)
        $PeOffset = $Reader.ReadInt32()
        if ($PeOffset -lt 64 -or ($PeOffset + 6) -gt $Stream.Length) {
            throw "Executable contains an invalid PE header offset: $Path"
        }
        [void]$Stream.Seek($PeOffset, [System.IO.SeekOrigin]::Begin)
        if ($Reader.ReadUInt32() -ne 0x00004550) { throw "Executable has no PE signature: $Path" }
        return $Reader.ReadUInt16()
    }
    finally {
        if ($Reader) { $Reader.Dispose() }
        elseif ($Stream) { $Stream.Dispose() }
    }
}

function Assert-FfmpegBundle {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $FfmpegPath = Join-Path $Directory "ffmpeg.exe"
    $FfprobePath = Join-Path $Directory "ffprobe.exe"
    foreach ($Path in @($FfmpegPath, $FfprobePath)) {
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
            throw "$Label is missing required executable: $Path"
        }
    }

    foreach ($Path in @($FfmpegPath, $FfprobePath)) {
        $Machine = Get-PeMachine -Path $Path
        if ($Machine -ne 0x8664) {
            $MachineHex = "0x{0:X4}" -f $Machine
            throw "$Label contains a non-x64 executable ($MachineHex): $Path"
        }
    }
    Write-Host "[OK] $Label contains x64 FFmpeg and FFprobe executables."

    $VersionOutput = Invoke-CheckedNative -Executable $FfmpegPath -Arguments @("-version") -Description "$Label ffmpeg -version"
    if ($VersionOutput -notmatch "(?m)^ffmpeg version ") {
        throw "$Label ffmpeg -version returned success but did not identify FFmpeg."
    }
    Write-Host "[OK] $Label $((($VersionOutput.Trim() -split "`r?`n")[0]))"

    $FfprobeVersion = Invoke-CheckedNative -Executable $FfprobePath -Arguments @("-version") -Description "$Label ffprobe -version"
    if ($FfprobeVersion -notmatch "(?m)^ffprobe version ") {
        throw "$Label ffprobe -version returned success but did not identify FFprobe."
    }
    Write-Host "[OK] $Label ffprobe -version completed successfully."

    $BuildConfiguration = Invoke-CheckedNative -Executable $FfmpegPath -Arguments @("-buildconf") -Description "$Label ffmpeg -buildconf"
    if ($BuildConfiguration -match "(?i)(?:^|\s)--enable-gpl(?=\s|$)") {
        throw "$Label FFmpeg build configuration contains --enable-gpl. Refusing to bundle a GPL build."
    }
    if ($BuildConfiguration -match "(?i)(?:^|\s)--enable-nonfree(?=\s|$)") {
        throw "$Label FFmpeg build configuration contains --enable-nonfree. Refusing to bundle a nonfree build."
    }
    if ($BuildConfiguration -notmatch "(?m)^\s*--arch=x86_64\s*$" -or
        $BuildConfiguration -notmatch "(?m)^\s*--target-os=mingw32\s*$") {
        throw "$Label FFmpeg build configuration does not identify Windows x86_64 (mingw32)."
    }
    if ($BuildConfiguration -notmatch "(?m)^\s*--enable-version3\s*$") {
        throw "$Label FFmpeg build configuration differs from the expected LGPL-3.0-or-later release."
    }
    Write-Host "[OK] $Label build configuration is Windows x64 and has no --enable-gpl or --enable-nonfree."

    $LicenseOutput = Invoke-CheckedNative -Executable $FfmpegPath -Arguments @("-L") -Description "$Label ffmpeg -L"
    if ($LicenseOutput -notmatch "(?is)GNU Lesser General Public License.*?either version\s+3\s+of the License") {
        throw "$Label license did not match expected $FfmpegLicense. Refusing to bundle it."
    }
    if ($LicenseOutput -match "GNU General Public License") {
        throw "$Label reports the GPL instead of expected $FfmpegLicense. Refusing to bundle it."
    }
    Write-Host "[OK] $Label reports the expected $FfmpegLicense license."

    $EncoderList = Invoke-CheckedNative -Executable $FfmpegPath -Arguments @("-hide_banner", "-encoders") -Description "$Label ffmpeg -encoders"
    if ($EncoderList -notmatch "(?m)^\s*V\S*\s+mpeg4\s") {
        throw "$Label FFmpeg build has no MP4 mpeg4 video encoder."
    }
    Write-Host "[OK] $Label mpeg4 video encoder is available."
}

if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) { throw "Python launcher '$Python' was not found." }
$PythonArgs = @()
if ([System.IO.Path]::GetFileNameWithoutExtension($Python) -eq "py") { $PythonArgs = @("-3.11") }
& $Python @PythonArgs -c "import sys; assert sys.version_info[:2] == (3,11), sys.version"
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 is required." }
if (-not $SkipClean) { Remove-Item -Recurse -Force .build-temp, dist -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force tools | Out-Null

$FfmpegZip = Join-Path $env:TEMP "clipforge-ffmpeg-lgpl-win64.zip"
Write-Host "Downloading pinned Windows x64 LGPL FFmpeg release $FfmpegReleaseTag..."
try {
    Invoke-WebRequest -Uri $FfmpegUrl -OutFile $FfmpegZip -TimeoutSec 180 -ErrorAction Stop
} catch {
    throw "Could not download FFmpeg archive '$FfmpegArchiveName' from $FfmpegUrl. $($_.Exception.Message)"
}
if (-not (Test-Path -LiteralPath $FfmpegZip -PathType Leaf)) {
    throw "FFmpeg download did not create the expected archive: $FfmpegZip"
}
$ActualSha256 = (Get-FileHash -LiteralPath $FfmpegZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualSha256 -ne $FfmpegSha256) {
    throw "FFmpeg archive SHA-256 mismatch. Expected $FfmpegSha256; got $ActualSha256. Refusing to extract it."
}
Write-Host "[OK] FFmpeg archive SHA-256 verified: $ActualSha256"

$Extract = Join-Path $env:TEMP "clipforge-ffmpeg-$FfmpegReleaseTag"
Remove-Item -Recurse -Force $Extract -ErrorAction SilentlyContinue
try {
    Expand-Archive -Path $FfmpegZip -DestinationPath $Extract -Force -ErrorAction Stop
} catch {
    throw "Could not extract the verified FFmpeg archive '$FfmpegArchiveName'. $($_.Exception.Message)"
}
$FfmpegMatches = @(Get-ChildItem $Extract -Filter ffmpeg.exe -File -Recurse)
$FfprobeMatches = @(Get-ChildItem $Extract -Filter ffprobe.exe -File -Recurse)
if ($FfmpegMatches.Count -ne 1) { throw "FFmpeg archive must contain exactly one ffmpeg.exe; found $($FfmpegMatches.Count)." }
if ($FfprobeMatches.Count -ne 1) { throw "FFmpeg archive must contain exactly one ffprobe.exe; found $($FfprobeMatches.Count)." }
$DllMatches = @(Get-ChildItem $Extract -Filter *.dll -File -Recurse)
if ($DllMatches.Count -eq 0) { throw "The selected FFmpeg shared archive contains no DLLs; refusing an incomplete bundle." }

# tools/ is reserved for bundled FFmpeg files. Remove stale DLLs and old license
# files first so a previous build cannot leave unrelated binaries in PyInstaller.
Get-ChildItem tools -File | Where-Object {
    $_.Extension -ieq ".dll" -or
    $_.Name -match "^(ffmpeg|ffprobe)\.exe$|^COPYING\.LGPLv[23](?:\.1)?$"
} | Remove-Item -Force
Copy-Item $FfmpegMatches[0].FullName (Join-Path $Root "tools\ffmpeg.exe") -Force
Copy-Item $FfprobeMatches[0].FullName (Join-Path $Root "tools\ffprobe.exe") -Force
foreach ($Dll in $DllMatches) {
    Copy-Item $Dll.FullName (Join-Path $Root ("tools\" + $Dll.Name)) -Force
}

# Validate the exact directory that PyInstaller will collect, including all
# shared DLLs required to launch the executables.
Assert-FfmpegBundle -Directory (Join-Path $Root "tools") -Label "Staged FFmpeg bundle"

$LicensePath = Join-Path $Root "tools\COPYING.LGPLv3"
try {
    Invoke-WebRequest -Uri $FfmpegLicenseUrl -OutFile $LicensePath -TimeoutSec 60 -ErrorAction Stop
} catch {
    throw "Could not download the official GNU LGPL v3 license text from $FfmpegLicenseUrl. $($_.Exception.Message)"
}
if (-not (Test-Path -LiteralPath $LicensePath -PathType Leaf) -or (Get-Item $LicensePath).Length -eq 0) {
    throw "The official LGPL v3 license text was not downloaded correctly."
}

Set-Content -Path (Join-Path $Root "THIRD_PARTY_NOTICES.txt") -Value @"
ClipForge AI third-party components

FFmpeg: $FfmpegLicense, Windows x64 shared build.
Archive: $FfmpegArchiveName
Archive SHA-256: $FfmpegSha256
Release: https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/tag/$FfmpegReleaseTag
License text: tools\COPYING.LGPLv3 ($FfmpegLicenseUrl)
FFmpeg source: https://ffmpeg.org/
Shared FFmpeg DLLs are bundled to support replacement under LGPL terms.

PySide6 / Qt, faster-whisper, CTranslate2 and PyAV are third-party components
under their respective licenses. Consult upstream license files.
"@ -Encoding UTF8

& $Python @PythonArgs -m venv .venv-build
if ($LASTEXITCODE -ne 0) { throw "Could not create .venv-build with Python 3.11." }
$VenvPython = Join-Path $Root ".venv-build\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) { throw "Virtual environment Python executable was not created: $VenvPython" }
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Build dependency bootstrap failed while upgrading pip." }
& $VenvPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }
$env:PATH = "$(Join-Path $Root 'tools');$env:PATH"
& $VenvPython build\check_dependencies.py
if ($LASTEXITCODE -ne 0) { throw "Dependency check failed." }
& $VenvPython -m PyInstaller --noconfirm --clean --workpath .build-temp clipforge.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$PortableDirectory = Join-Path $Root "dist\ClipForgeAI"
$PackagedToolsDirectory = Join-Path $PortableDirectory "_internal\tools"
if (-not (Test-Path -LiteralPath $PackagedToolsDirectory -PathType Container)) {
    # PyInstaller 6.12+ stores one-folder payload files in _internal. Older 6.x
    # releases place them beside the executable; both layouts match sys._MEIPASS.
    $PackagedToolsDirectory = Join-Path $PortableDirectory "tools"
}
foreach ($RequiredFile in @("ffmpeg.exe", "ffprobe.exe", "COPYING.LGPLv3")) {
    $PackagedPath = Join-Path $PackagedToolsDirectory $RequiredFile
    if (-not (Test-Path -LiteralPath $PackagedPath -PathType Leaf)) {
        throw "PyInstaller portable build is missing required FFmpeg file: $PackagedPath"
    }
}
Assert-FfmpegBundle -Directory $PackagedToolsDirectory -Label "PyInstaller portable bundle"
Copy-Item README.md, AI_MODELS.md, THIRD_PARTY_NOTICES.txt, INSTALL_AI.bat -Destination $PortableDirectory -Force
Write-Host "Portable folder created: dist\ClipForgeAI" -ForegroundColor Green

$IsccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$IsccPath = if ($IsccCommand) { $IsccCommand.Source } else { $null }
if (-not $IsccPath) {
    $Candidate = "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $Candidate) { $IsccPath = $Candidate }
}
if ($IsccPath) {
    New-Item -ItemType Directory -Force dist\installer | Out-Null
    & $IsccPath installer\ClipForgeAI.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
    $Installer = Join-Path $Root "dist\installer\ClipForgeAI-Setup-0.3.0-x64.exe"
    if (-not (Test-Path -LiteralPath $Installer -PathType Leaf) -or (Get-Item $Installer).Length -eq 0) {
        throw "Inno Setup reported success but did not create the expected installer: $Installer"
    }
    Write-Host "[OK] Inno Setup installer created: dist\installer\ClipForgeAI-Setup-0.3.0-x64.exe"
} else { Write-Warning "Inno Setup 6 not found; installer skipped." }
