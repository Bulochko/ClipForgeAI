import { toVoiceOpus, toWav } from './ffmpeg.mjs';

const TTS_ENDPOINT = 'https://translate.google.com/translate_tts';
const TTS_LIMIT = 180;

/**
 * Free TTS through the Google Translate endpoint.
 * Long texts are split into chunks whose MP3 frames are concatenated,
 * then re-encoded into OGG/Opus for a Telegram voice message.
 */
export async function textToSpeech(text, { lang } = {}) {
  const clean = String(text ?? '').trim();
  if (!clean) throw new Error('Нечего озвучивать.');

  const language = lang ?? (/[А-Яа-яЁё]/.test(clean) ? 'ru' : 'en');
  const chunks = splitForTts(clean);
  const parts = [];

  for (const chunk of chunks) {
    parts.push(await fetchTtsChunk(chunk, language));
  }

  const mp3 = Buffer.concat(parts);
  return toVoiceOpus(mp3, 'mp3');
}

async function fetchTtsChunk(text, lang) {
  const url =
    `${TTS_ENDPOINT}?ie=UTF-8&client=tw-ob&tl=${encodeURIComponent(lang)}` +
    `&q=${encodeURIComponent(text)}`;

  const response = await fetch(url, {
    headers: { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' },
    signal: AbortSignal.timeout(30_000),
  });

  if (!response.ok) throw new Error(`TTS: HTTP ${response.status}`);
  const buffer = Buffer.from(await response.arrayBuffer());
  if (buffer.length < 512) throw new Error('TTS вернул пустой звук.');
  return buffer;
}

function splitForTts(text) {
  const sentences = text.replace(/\s+/g, ' ').match(/[^.!?…]+[.!?…]?/g) ?? [text];
  const chunks = [];
  let current = '';

  for (const sentence of sentences) {
    const piece = sentence.trim();
    if (!piece) continue;
    if (piece.length > TTS_LIMIT) {
      if (current) {
        chunks.push(current);
        current = '';
      }
      chunks.push(...wrap(piece, TTS_LIMIT));
      continue;
    }
    if ((current + ' ' + piece).trim().length > TTS_LIMIT) {
      chunks.push(current.trim());
      current = piece;
    } else {
      current = `${current} ${piece}`.trim();
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks.slice(0, 12);
}

function wrap(text, limit) {
  const words = text.split(' ');
  const out = [];
  let line = '';
  for (const word of words) {
    if ((line + ' ' + word).trim().length > limit) {
      if (line) out.push(line.trim());
      line = word;
    } else {
      line = `${line} ${word}`.trim();
    }
  }
  if (line.trim()) out.push(line.trim());
  return out;
}

/**
 * Speech recognition through Groq's free Whisper tier.
 * Accepts any Telegram audio/video payload; converts it to 16 kHz mono WAV first.
 */
export async function speechToText(input, { inputExt = 'ogg', lang = 'ru' } = {}) {
  const key = (process.env.GROQ_API_KEY ?? '').trim();
  if (!key) {
    throw new Error('Распознавание речи не настроено: добавь GROQ_API_KEY в .env (бесплатно на console.groq.com).');
  }

  const wav = await toWav(input, inputExt);
  const form = new FormData();
  form.set('file', new Blob([wav], { type: 'audio/wav' }), 'audio.wav');
  form.set('model', (process.env.GROQ_STT_MODEL ?? '').trim() || 'whisper-large-v3-turbo');
  form.set('response_format', 'json');
  if (lang) form.set('language', lang);

  const response = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
    method: 'POST',
    headers: { authorization: `Bearer ${key}` },
    body: form,
    signal: AbortSignal.timeout(120_000),
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(`Whisper: HTTP ${response.status} ${payload?.error?.message ?? ''}`.trim());
  }
  const text = String(payload?.text ?? '').trim();
  if (!text) throw new Error('Речь не распознана — возможно, запись пустая.');
  return text;
}
