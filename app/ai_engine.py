from __future__ import annotations
import json
import urllib.request
import urllib.error

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_LLM = "qwen3:4b"


def transcribe_video(path: str, model_size: str = "small") -> tuple[list[dict], str]:
    """Transcribe locally. Prefer CUDA when its runtime is available; fall back to CPU int8."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Не установлен faster-whisper. Запусти INSTALL_AI.bat и повтори анализ.") from exc

    model = None
    backend = "CPU / INT8"
    try:
        model = WhisperModel(model_size, device="cuda", compute_type="int8_float16")
        backend = "NVIDIA GPU / INT8-FP16"
    except Exception:
        model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=8)

    segments, info = model.transcribe(path, beam_size=3, vad_filter=True)
    result = [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()} for s in segments if s.text.strip()]
    del model
    return result, f"{backend}; язык: {info.language}"


def _fallback_candidates(segments: list[dict], duration: float) -> list[dict]:
    """Speech-window fallback when Ollama is not installed or unavailable."""
    windows = []
    if not segments:
        return windows
    start = segments[0]["start"]
    end = start
    texts = []
    for seg in segments:
        if seg["start"] - end > 5 or seg["end"] - start > 48:
            if end - start >= 12:
                windows.append({"start": max(0, start), "end": min(duration, end), "score": 55, "reason": "Связный речевой фрагмент; требуется ручная оценка"})
            start, texts = seg["start"], []
        end = seg["end"]
        texts.append(seg["text"])
    if end - start >= 12:
        windows.append({"start": max(0, start), "end": min(duration, end), "score": 55, "reason": "Связный речевой фрагмент; требуется ручная оценка"})
    return windows[:20]


def analyze_transcript(segments: list[dict], duration: float, model: str = DEFAULT_LLM) -> tuple[list[dict], str]:
    transcript = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)
    if not transcript.strip():
        return [], "Речь не обнаружена"
    transcript = transcript[:18000]
    prompt = (
        "You are an expert short-form video editor. Find up to 8 self-contained, compelling clips in this transcript. "
        "Prefer hooks, surprising claims, useful tips, punchlines, emotional peaks, clear mini-stories. "
        "Each clip should usually be 15-55 seconds. Use only timestamps present in the transcript; do not invent content. "
        "Return ONLY valid JSON: {\"clips\":[{\"start\":number,\"end\":number,\"score\":integer,\"title\":string,\"reason\":string}]}\n\n"
        f"VIDEO_DURATION_SECONDS: {duration:.1f}\nTRANSCRIPT:\n{transcript}"
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 1400},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = payload.get("message", {}).get("content", "{}")
        parsed = json.loads(raw)
        clips = []
        for item in parsed.get("clips", []):
            start, end = float(item.get("start", 0)), float(item.get("end", 0))
            if start < 0 or end <= start or start > duration:
                continue
            clips.append({
                "start": round(start, 2), "end": round(min(end, duration), 2),
                "score": max(1, min(100, int(item.get("score", 50)))),
                "title": str(item.get("title", "AI clip"))[:100],
                "reason": str(item.get("reason", ""))[:240],
            })
        clips.sort(key=lambda x: x["score"], reverse=True)
        if clips:
            return clips[:8], f"AI-анализ: {model}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError):
        pass
    return _fallback_candidates(segments, duration), "Локальная эвристика (Ollama недоступна)"


def run_analysis(path: str, duration: float, whisper_model: str = "small", llm_model: str = DEFAULT_LLM):
    segments, backend = transcribe_video(path, whisper_model)
    clips, analyzer = analyze_transcript(segments, duration, llm_model)
    return segments, clips, f"{backend}; {analyzer}"
