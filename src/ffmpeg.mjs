import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

/** Locate ffmpeg: explicit override, then PATH, then a WinGet package install. */
function resolveFfmpeg() {
  const override = (process.env.FFMPEG_PATH ?? '').trim();
  if (override && existsSync(override)) return override;

  const base = join(process.env.LOCALAPPDATA ?? '', 'Microsoft', 'WinGet', 'Packages');
  if (base && existsSync(base)) {
    for (const entry of readdirSync(base)) {
      if (!/^Gyan\.FFmpeg/i.test(entry)) continue;
      const root = join(base, entry);
      for (const sub of readdirSync(root)) {
        const candidate = join(root, sub, 'bin', 'ffmpeg.exe');
        if (existsSync(candidate)) return candidate;
      }
    }
  }
  return 'ffmpeg';
}

const FFMPEG = resolveFfmpeg();

function exec(args, timeoutMs = 180_000) {
  return new Promise((resolve, reject) => {
    const child = spawn(FFMPEG, args, { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error('ffmpeg: превышено время обработки'));
    }, timeoutMs);

    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk) => {
      stderr += chunk;
    });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error.code === 'ENOENT' ? new Error('ffmpeg не найден. Установи FFmpeg и добавь в PATH.') : error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code === 0) return resolve();
      reject(new Error(`ffmpeg код ${code}: ${stderr.split(/\r?\n/).filter(Boolean).slice(-2).join(' ').slice(0, 300)}`));
    });
  });
}

/** Convert a media buffer through a temp file and return the result buffer. */
async function convert({ input, inputExt, outputExt, args }) {
  const dir = mkdtempSync(join(tmpdir(), 'lyra-'));
  const inPath = join(dir, `in.${inputExt}`);
  const outPath = join(dir, `out.${outputExt}`);
  writeFileSync(inPath, input);
  try {
    await exec(['-hide_banner', '-loglevel', 'error', '-y', '-i', inPath, ...args, outPath]);
    return readFileSync(outPath);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

/** Telegram voice messages: mono OGG/Opus. */
export function toVoiceOpus(input, inputExt = 'mp3') {
  return convert({
    input,
    inputExt,
    outputExt: 'ogg',
    args: ['-c:a', 'libopus', '-b:a', '48k', '-ar', '48000', '-ac', '1'],
  });
}

/** 16 kHz mono WAV — a safe upload format for speech recognition. */
export function toWav(input, inputExt = 'ogg') {
  return convert({
    input,
    inputExt,
    outputExt: 'wav',
    args: ['-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le'],
  });
}

/** Telegram stickers: 512×512 WebP with transparent padding. */
export function toStickerWebp(input, inputExt = 'jpg') {
  return convert({
    input,
    inputExt,
    outputExt: 'webp',
    args: [
      '-vf',
      'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=black@0',
      '-c:v',
      'libwebp',
      '-q:v',
      '80',
    ],
  });
}

export async function ffmpegAvailable() {
  try {
    await exec(['-version']);
    return true;
  } catch {
    return false;
  }
}
