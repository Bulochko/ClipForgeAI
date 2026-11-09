/**
 * Image generation through the current Pollinations API.
 * The API key is kept server-side in POLLINATIONS_API_KEY.
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
  const key = (process.env.POLLINATIONS_API_KEY ?? '').trim();
  if (!key) {
    throw new Error('Для генерации изображений нужен POLLINATIONS_API_KEY. Добавь ключ Pollinations в .env.');
  }

  const params = new URLSearchParams({
    width: String(clamp(width, 256, 1536)),
    height: String(clamp(height, 256, 1536)),
    nologo: 'true',
    model,
  });
  if (seed !== undefined) params.set('seed', String(seed));

  const url = `https://gen.pollinations.ai/image/${encodeURIComponent(prompt.trim())}?${params}`;
  const response = await fetch(url, {
    headers: { authorization: `Bearer ${key}` },
    signal: AbortSignal.timeout(timeoutMs),
  });

  if (!response.ok) {
    throw new Error(`Pollinations: HTTP ${response.status}`);
  }

  const buffer = Buffer.from(await response.arrayBuffer());
  if (buffer.length < 1024) throw new Error('Pollinations вернул пустое изображение.');

  const contentType = (response.headers.get('content-type') ?? '').split(';')[0].trim().toLowerCase();
  if (!['image/jpeg', 'image/png'].includes(contentType)) {
    throw new Error(`Pollinations вернул неподдерживаемый тип данных: ${contentType || 'неизвестен'}`);
  }
  if (buffer.length > 10 * 1024 * 1024) {
    throw new Error('Изображение превышает лимит Telegram в 10 МБ.');
  }

  const extension = contentType === 'image/png' ? 'png' : 'jpg';
  return { buffer, contentType, extension, url };
}

function clamp(value, min, max) {
  return Math.min(Math.max(Number(value) || min, min), max);
}
