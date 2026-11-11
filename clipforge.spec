from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)
APP = ROOT / "app"
TOOLS = ROOT / "tools"
datas = [(str(ROOT / "README.md"), "."), (str(ROOT / "AI_MODELS.md"), ".")]
binaries = []
for name in ("ffmpeg.exe", "ffprobe.exe"):
    path = TOOLS / name
    if not path.is_file():
        raise SystemExit(f"Required bundled dependency is missing: {path}")
    binaries.append((str(path), "tools"))
for path in TOOLS.glob("*.dll"):
    binaries.append((str(path), "tools"))
license_path = TOOLS / "COPYING.LGPLv3"
if license_path.is_file():
    datas.append((str(license_path), "tools"))
hiddenimports = ["shiboken6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]
for package in ("faster_whisper", "ctranslate2", "av", "tokenizers", "huggingface_hub"):
    package_datas, package_bins, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_bins
    hiddenimports += package_hidden
a = Analysis([str(APP / "main.py")], pathex=[str(APP), str(ROOT)],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["tkinter", "unittest", "pytest", "IPython", "notebook"], noarchive=False)

# PyInstaller resolves native imports using PATH. A host tool such as Poppler
# can expose an incompatible ICU DLL (for example ICU 78 exports suffixed
# symbols, while the Qt wheel imports the Windows ICU compatibility names).
# PySide6 works with the system ICU on supported Windows versions, so never
# ship an unrelated ICU runtime from the build host.
def is_icu_runtime(entry):
    name = Path(str(entry[0])).name.lower()
    return name.startswith("icu") and name.endswith(".dll")

a.binaries = [entry for entry in a.binaries if not is_icu_runtime(entry)]
a.datas = [entry for entry in a.datas if not is_icu_runtime(entry)]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ClipForge AI",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ClipForgeAI")
