import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';

import { loadConfig } from './config.mjs';
import { Telegram } from './telegram.mjs';
import { availableProviders, chat } from './providers.mjs';
import { ffmpegAvailable } from './ffmpeg.mjs';
import { generateImage } from './image.mjs';

/**
 * Environment doctor: verifies everything the bot needs before it is deployed.
 * Run it on a fresh server first: `node src/doctor.mjs [--deep]`.
 * Exit code 0 means the bot has a working minimum; 1 means something critical is missing.
 */
const deep = process.argv.includes('--deep');
const config = loadConfig();
const results = [];

function record(name, ok, detail) {
  results.push({ name, ok, detail });
  const mark = ok === null ? 'SKIP' : ok ? 'OK  ' : 'FAIL';
  console.log(`${mark} ${name}${detail ? ` — ${detail}` : ''}`);
}

console.log('Lyra AI doctor');
console.log(`режим: ${config.mode}, провайдер по умолчанию: ${config.defaultProvider}\n`);

// 1. Configuration
record('токен бота задан', Boolean(config.botToken), config.botToken ? 'скрыт' : 'TELEGRAM_BOT_TOKEN пуст');

const providers = availableProviders();
const apiProviders = providers.filter((item) => item.kind !== 'agent');
record(
  'ключи провайдеров',
  apiProviders.length > 0 || providers.some((item) => item.kind === 'agent'),
  providers.map((item) => item.name).join(', ') || 'нет ни одного',
);

if (config.mode === 'webhook') {
  record('webhook настроен', Boolean(config.webhookUrl), config.webhookUrl || 'WEBHOOK_URL пуст');
  record('webhook secret', Boolean(config.webhookSecret), config.webhookSecret ? 'задан' : 'рекомендуется задать');
}

// 2. Telegram reachability + token validity
if (config.botToken) {
  try {
    const tg = new Telegram({ token: config.botToken, apiBase: config.apiBase, requestTimeoutMs: 20_000 });
    const me = await tg.call('getMe', {}, { retries: 0 });
    record('Telegram API', true, `@${me.username} (${me.first_name})`);
    if (config.mode === 'webhook') {
      const info = await tg.getWebhookInfo().catch(() => null);
      if (info) {
        record('текущий webhook', true, `${info.url || 'не задан'} pending=${info.pending_update_count} last_error=${info.last_error_message ?? 'нет'}`);
      }
    }
  } catch (error) {
    record('Telegram API', false, error.message);
  }
}

// 3. ffmpeg for voice and stickers
record('ffmpeg', await ffmpegAvailable(), 'нужен для голоса, видеокружков и стикеров');

// 4. Writable state directory
try {
  mkdirSync(join(config.root, 'data'), { recursive: true });
  const probe = join(config.root, 'data', 'doctor.tmp');
  writeFileSync(probe, 'ok');
  rmSync(probe, { force: true });
  record('запись в data/', true, join(config.root, 'data'));
} catch (error) {
  record('запись в data/', false, error.message);
}

// 5. Optional live checks (cost a few tokens / one image)
if (deep) {
  for (const provider of apiProviders) {
    try {
      const started = Date.now();
      const answer = await chat({
        provider: provider.name,
        system: 'Ответь одним словом.',
        messages: [{ role: 'user', content: 'пинг' }],
      });
      record(`провайдер ${provider.name}`, true, `${Date.now() - started} мс: ${answer.slice(0, 40)}`);
    } catch (error) {
      record(`провайдер ${provider.name}`, false, error.message);
    }
  }

  try {
    const { buffer } = await generateImage({ prompt: 'тестовая картинка', width: 256, height: 256 });
    record('генерация картинок', true, `${Math.round(buffer.length / 1024)} КБ`);
  } catch (error) {
    record('генерация картинок', false, error.message);
  }
} else {
  record('живые проверки провайдеров', null, 'запусти с --deep');
}

const failed = results.filter((item) => item.ok === false);
console.log(`\nитого: ${results.filter((item) => item.ok === true).length} ок, ${failed.length} проблем`);
if (failed.length > 0) {
  console.log('критичные проблемы:', failed.map((item) => item.name).join(', '));
  process.exitCode = 1;
}
