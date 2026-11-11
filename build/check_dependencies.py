from __future__ import annotations
import importlib.util, os, shutil, sys

def check(name, ok, detail=""):
    print(f"[{'OK' if ok else 'MISSING'}] {name}" + (f" — {detail}" if detail else ""))
    return ok

def main():
    results = [
        check("Windows x64", os.name == "nt" and sys.maxsize > 2**32),
        check("Python 3.11+", sys.version_info >= (3, 11), sys.version.split()[0]),
    ]
    for module in ("PySide6", "faster_whisper", "ctranslate2"):
        results.append(check(module, importlib.util.find_spec(module) is not None))
    for exe in ("ffmpeg", "ffprobe"):
        path = shutil.which(exe)
        results.append(check(exe, bool(path), path or "not found in PATH"))
    ollama = shutil.which("ollama")
    check("Ollama (optional)", bool(ollama), ollama or "install separately for transcript scoring")
    if not all(results):
        print("\nDependency check failed. Install missing required components and retry.")
        return 1
    print("\nRequired dependencies are present.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
