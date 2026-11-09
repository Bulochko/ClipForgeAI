/**
 * Minimal Telegram Bot API client on top of global fetch.
 * Retries on 429 and transient network errors; never throws on Telegram "ok: false"
 * unless the caller asks for it.
 */
export class Telegram {
  constructor({ token, apiBase = 'https://api.telegram.org', requestTimeoutMs = 70_000 }) {
    this.token = token;
    this.apiBase = apiBase.replace(/\/+$/, '');
    this.requestTimeoutMs = requestTimeoutMs;
  }

  async call(method, params = {}, { retries = 3 } = {}) {
    const url = `${this.apiBase}/bot${this.token}/${method}`;
    let attempt = 0;

    for (;;) {
      attempt += 1;
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(params),
          signal: AbortSignal.timeout(this.requestTimeoutMs),
        });

        const payload = await response.json().catch(() => null);

        if (response.status === 401) {
          throw new Error('Telegram rejected the bot token (401 Unauthorized). Check TELEGRAM_BOT_TOKEN.');
        }
        if (response.status === 429) {
          const wait = Number(payload?.parameters?.retry_after ?? 5) * 1000;
          if (attempt > retries) throw new Error(`Telegram rate limit, retry_after=${wait / 1000}s`);
          await sleep(wait);
          continue;
        }
        if (!response.ok) {
          throw new Error(`Telegram ${method} failed: HTTP ${response.status} ${JSON.stringify(payload)}`);
        }
        if (payload && payload.ok === false) {
          throw new Error(`Telegram ${method} failed: ${payload.description ?? 'unknown error'}`);
        }
        return payload?.result;
      } catch (error) {
        const transient =
          error?.name === 'TimeoutError' ||
          error?.name === 'TypeError' ||
          /fetch failed|ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN/i.test(String(error?.message));
        if (!transient || attempt > retries) throw error;
        await sleep(Math.min(2000 * attempt, 10_000));
      }
    }
  }

  getUpdates(offset, timeoutSeconds = 50) {
    return this.call(
      'getUpdates',
      { offset, timeout: timeoutSeconds, allowed_updates: ['message'] },
      { retries: 2 },
    );
  }

  sendMessage(chatId, text, extra = {}) {
    return this.call('sendMessage', {
      chat_id: chatId,
      text: truncate(text, 4000),
      disable_web_page_preview: true,
      ...extra,
    });
  }

  sendChatAction(chatId, action = 'typing') {
    return this.call('sendChatAction', { chat_id: chatId, action }).catch(() => undefined);
  }

  /** Upload a generated picture as a photo message. */
  async sendPhoto(chatId, { buffer, filename = 'image.jpg', contentType = 'image/jpeg', caption }) {
    const form = new FormData();
    form.set('chat_id', String(chatId));
    if (caption) form.set('caption', truncate(caption, 1000));
    form.set('photo', new Blob([buffer], { type: contentType }), filename);

    const response = await fetch(`${this.apiBase}/bot${this.token}/sendPhoto`, {
      method: 'POST',
      body: form,
      signal: AbortSignal.timeout(120_000),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok || payload?.ok === false) {
      throw new Error(`sendPhoto: HTTP ${response.status} ${payload?.description ?? ''}`.trim());
    }
    return payload.result;
  }

  /** Upload an OGG/Opus buffer as a voice message. */
  async sendVoice(chatId, { buffer, filename = 'voice.ogg', duration }) {
    const form = new FormData();
    form.set('chat_id', String(chatId));
    if (duration) form.set('duration', String(Math.round(duration)));
    form.set('voice', new Blob([buffer], { type: 'audio/ogg' }), filename);
    return this.upload('sendVoice', form);
  }

  /** Upload a WebP buffer as a sticker. */
  async sendSticker(chatId, { buffer, filename = 'sticker.webp', emoji }) {
    const form = new FormData();
    form.set('chat_id', String(chatId));
    if (emoji) form.set('emoji', emoji);
    form.set('sticker', new Blob([buffer], { type: 'image/webp' }), filename);
    return this.upload('sendSticker', form);
  }

  async upload(method, form) {
    const response = await fetch(`${this.apiBase}/bot${this.token}/${method}`, {
      method: 'POST',
      body: form,
      signal: AbortSignal.timeout(120_000),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok || payload?.ok === false) {
      throw new Error(`${method}: HTTP ${response.status} ${payload?.description ?? ''}`.trim());
    }
    return payload.result;
  }

  /** Resolve a Telegram file_id to a temporary download path. */
  async getFile(fileId) {
    const result = await this.call('getFile', { file_id: fileId });
    return result?.file_path;
  }

  /** Download a file by its Telegram path into a Buffer. */
  /** Download a file by its Telegram path into a Buffer. */
  async downloadFile(filePath) {
    const response = await fetch(`${this.apiBase}/file/bot${this.token}/${filePath}`, {
      signal: AbortSignal.timeout(120_000),
    });
    if (!response.ok) throw new Error(`downloadFile: HTTP ${response.status}`);
    return Buffer.from(await response.arrayBuffer());
  }

  /** Switch Telegram to webhook delivery (used on a VPS behind HTTPS). */
  setWebhook(url, { secretToken, maxConnections = 1 } = {}) {
    return this.call('setWebhook', {
      url,
      ...(secretToken ? { secret_token: secretToken } : {}),
      max_connections: maxConnections,
      allowed_updates: ['message'],
    });
  }

  deleteWebhook() {
    return this.call('deleteWebhook', {});
  }

  getWebhookInfo() {
    return this.call('getWebhookInfo', {});
  }
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function truncate(text, limit) {
  const value = String(text ?? '');
  return value.length <= limit ? value : `${value.slice(0, limit - 1)}…`;
}

/** Split long answers into several Telegram messages on paragraph boundaries. */
export function splitMessage(text, limit = 4000) {
  const value = String(text ?? '').trim();
  if (value.length <= limit) return [value];

  const chunks = [];
  let rest = value;
  while (rest.length > limit) {
    const window = rest.slice(0, limit);
    const cut = Math.max(window.lastIndexOf('\n\n'), window.lastIndexOf('\n'), window.lastIndexOf('. '));
    const end = cut > limit * 0.4 ? cut + 1 : limit;
    chunks.push(rest.slice(0, end).trim());
    rest = rest.slice(end).trim();
  }
  if (rest) chunks.push(rest);
  return chunks;
}
