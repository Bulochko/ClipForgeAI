/**
 * Free image generation through Pollinations.ai: no API key required.
 * Returns raw bytes so the bot can upload them straight to Telegram.
 */
export async function generateImage({
  prompt,
  width = 1024,
  height = 1024,
  seed,
  model = 'flux',
  timeoutMs = 120_000,
}) {
  if (!prompt || !prompt.trim()) throw new Error('Пустой запрос к генератору изображений.');

  const params = new URLSearchParams({
    width: String(clamp(width, 256, 1536)),
    height: String(clamp(height, 256, 1536)),
    nologo: 'true',
    model,
  });
  if (seed !== undefined) params.set('seed', String(seed));

  const url = `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt.trim())}?${params}`;
  const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });

  if (!response.ok) {
    throw new Error(`Pollinations: HTTP ${response.status}`);
  }

  const buffer = Buffer.from(await response.arrayBuffer());
  if (buffer.length < 1024) throw new Error('Pollinations вернул пустое изображение.');

  const contentType = response.headers.get('content-type') ?? 'image/jpeg';
  const extension = contentType.includes('png') ? 'png' : 'jpg';
  return { buffer, contentType, extension, url };
}

function clamp(value, min, max) {
  return Math.min(Math.max(Number(value) || min, min), max);
}
