import { generateImage } from './image.mjs';
import { toStickerWebp } from './ffmpeg.mjs';

/**
 * Static Telegram sticker: a 512×512 WebP with transparent padding.
 * Pollinations draws the artwork, ffmpeg fits it into the sticker canvas.
 */
export async function makeSticker({ prompt, seed }) {
  const { buffer, extension } = await generateImage({
    prompt,
    width: 512,
    height: 512,
    seed,
    model: 'flux',
  });
  const webp = await toStickerWebp(buffer, extension);
  if (webp.length < 1024) throw new Error('Стикер получился пустым.');
  return webp;
}
