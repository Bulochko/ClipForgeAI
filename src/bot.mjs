import { mkdirSync, readFileSync, writeFileSync, readdirSync, renameSync, rmSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { loadConfig, isChatAllowed } from './config.mjs';
import { Telegram, sleep, splitMessage, truncate } from './telegram.mjs';
import { askAgent, describeLauncher, agentAvailable } from './agent.mjs';
import { chat as runChat, PROVIDERS, availableProviders } from './providers.mjs';
import { generateImage } from './image.mjs';
import { textToSpeech, speechToText } from './speech.mjs';
import { makeSticker } from './sticker.mjs';
import { ffmpegAvailable } from './ffmpeg.mjs';
import { startWebhookServer } from './webhook.mjs';
import { createLimiter } from './ratelimit.mjs';

const config = loadConfig();
if (!['polling', 'webhook'].includes(config.mode)) {
  die('MODE должен быть polling или webhook.');
}
const stateDir = join(config.root, 'data');
mkdirSync(stateDir, { recursive: true });
const offsetFile = join(stateDir, 'offset.json');
const webhookQueueDir = join(stateDir, 'webhook-queue');

if (!config.botToken) die('TELEGRAM_BOT_TOKEN не задан. Впиши токен от @BotFather в .env.');
if (config.deepseekKey) process.env.DEEPSEEK_API_KEY = config.deepseekKey;

const PROVIDER_KEY_ENVS = ['DEEPSEEK_API_KEY', 'GEMINI_API_KEY', 'GROQ_API_KEY', 'OPENROUTER_API_KEY'];
if (!PROVIDER_KEY_ENVS.some((name) => process.env[name]) && !agentAvailable()) {
  die('Не задан ни один ключ провайдера. Добавь GEMINI_API_KEY, GROQ_API_KEY или DEEPSEEK_API_KEY в .env.');
}

const tg = new Telegram({ token: config.botToken, apiBase: config.apiBase });
const history = new Map(); // chatId -> [{ role, content }]
const providers = new Map(); // chatId -> provider name
const busy = new Map(); // chatId -> true while a reply is being produced
const limiter = createLimiter({ limit: config.rateLimitPerMin, windowMs: 60_000 });
let offset = loadOffset();

const SYSTEM_PROMPT =
  'Ты Lyra — дружелюбный ассистент в Telegram. Отвечай по-русски, коротко и по делу, ' +
  'без лишних вступлений. Если просят код — давай рабочий код.';

if (config.proxy) {
  console.warn(
    `[warn] TELEGRAM_PROXY=${config.proxy} задан, но fetch учитывает прокси только через ` +
      'NODE_USE_ENV_PROXY=1 / --use-env-proxy. Включай это в run.cmd или используй системный VPN.',
  );
}

console.log(`Lyra AI bot запущен. Агент: ${describeLauncher()}`);
console.log(`Рабочая папка агента: ${config.workspace}`);
console.log(
  `Доступные провайдеры: ${availableProviders()
    .map((item) => item.name)
    .join(', ')} (по умолчанию: ${config.defaultProvider})`,
);

if (!(await ffmpegAvailable())) {
  console.warn('[warn] ffmpeg не найден: голосовые, видеокружки и стикеры будут недоступны.');
}

const probe = new Telegram({ token: config.botToken, apiBase: config.apiBase, requestTimeoutMs: 15_000 });probe
  .call('getMe', {}, { retries: 0 })
  .then((me) => console.log(`Карточка бота: @${me?.username ?? '?'}`))
  .catch((error) => console.error(`[getMe] ${error.message}`));

if (config.mode === 'webhook') {
  if (!config.webhookUrl) die('MODE=webhook требует WEBHOOK_URL — публичный HTTPS-адрес эндпоинта.');
  if (!/^[A-Za-z0-9_-]{1,256}$/.test(config.webhookSecret)) {
    die('WEBHOOK_SECRET обязателен и должен содержать 1–256 символов: A–Z, a–z, 0–9, _ или -.');
  }
  mkdirSync(webhookQueueDir, { recursive: true });
  void processWebhookQueue();
  await startWebhookServer({
    port: config.webhookPort,
    secret: config.webhookSecret,
    onUpdate: enqueueWebhookUpdate,
  });
  await tg.setWebhook(config.webhookUrl, { secretToken: config.webhookSecret });
  console.log(`Режим webhook: порт ${config.webhookPort}, Telegram -> ${config.webhookUrl}`);
} else {
  await tg.deleteWebhook().catch(() => undefined);
  void poll();
}

async function poll() {
  let failures = 0;
  for (;;) {
    try {
      const updates = await tg.getUpdates(offset, 50);
      failures = 0;
      for (const update of updates ?? []) {
        const processed = await safeHandle(update);
        if (!processed) {
          // Keep the same offset so Telegram redelivers this update on the next poll.
          await sleep(1000);
          break;
        }
        offset = update.update_id + 1;
        saveOffset(offset);
      }
    } catch (error) {
      failures += 1;
      console.error(`[poll] ${error.message}`);
      if (/401/.test(error.message)) process.exit(1);
      await sleep(Math.min(2000 * failures, 30_000));
    }
  }
}

/**
 * Never let a single failed update take the process down: a send error for one
 * chat must not stop the bot for everyone else.
 */
async function safeHandle(update) {
  try {
    await handleUpdate(update);
    return true;
  } catch (error) {
    console.error(`[update] ${error?.message ?? error}`);
    return false;
  }
}

/** Persist webhook updates before returning HTTP 200 to Telegram. */
function enqueueWebhookUpdate(update) {
  const updateId = Number(update?.update_id);
  if (!Number.isSafeInteger(updateId) || updateId < 0) {
    throw new Error('Telegram update has no valid update_id.');
  }

  const filePath = join(webhookQueueDir, `${updateId}.json`);
  if (existsSync(filePath)) return;
  const temporaryPath = `${filePath}.${process.pid}.tmp`;
  writeFileSync(temporaryPath, JSON.stringify(update), 'utf8');
  renameSync(temporaryPath, filePath);
}

/** Process the durable webhook queue sequentially; failed updates stay on disk. */
async function processWebhookQueue() {
  for (;;) {
    let files;
    try {
      files = readdirSync(webhookQueueDir)
        .filter((name) => /^\d+\.json$/.test(name))
        .sort((a, b) => Number(a.slice(0, -5)) - Number(b.slice(0, -5)));
    } catch (error) {
      console.error(`[webhook-queue] ${error.message}`);
      await sleep(1000);
      continue;
    }

    if (files.length === 0) {
      await sleep(500);
      continue;
    }

    const filePath = join(webhookQueueDir, files[0]);
    let update;
    try {
      update = JSON.parse(readFileSync(filePath, 'utf8'));
    } catch (error) {
      console.error(`[webhook-queue] removing unreadable update: ${error.message}`);
      rmSync(filePath, { force: true });
      continue;
    }

    if (await safeHandle(update)) {
      rmSync(filePath, { force: true });
    } else {
      await sleep(1000);
    }
  }
}

async function handleUpdate(update) {
  const message = update.message;
  const chatId = message?.chat?.id;
  if (!chatId) return;

  if (!isChatAllowed({
    chatId,
    allowedChatIds: config.allowedChatIds,
    allowPublicChats: config.allowPublicChats,
    text: message.text ?? '',
  })) {
    console.log(`[deny] chat=${chatId} is not authorized`);
    return;
  }

  if (!limiter.allow(chatId)) {
    const wait = limiter.retryAfter(chatId);
    console.log(`[limit] chat=${chatId} retry_after=${wait}s`);
    await tg.sendMessage(chatId, `Слишком часто. Подожди ${wait} с и повтори.`);
    return;
  }

  const audio = message.voice ?? message.video_note ?? message.audio;
  if (audio) {
    await handleAudioMessage(chatId, audio, message);
    return;
  }

  const text = (message?.text?.trim() ?? '').replace(/^\/([a-z0-9_]+)@\w+/i, '/$1');
  if (!text) return;

  if (text === '/start' || text === '/help') {
    await tg.sendMessage(chatId, helpText());
    return;
  }
  if (text === '/reset') {
    history.delete(chatId);
    await tg.sendMessage(chatId, 'Контекст очищен.');
    return;
  }
  if (text === '/id') {
    await tg.sendMessage(chatId, `chat_id: ${chatId}`);
    return;
  }
  if (text === '/model' || text.startsWith('/model ')) {
    await handleModelCommand(chatId, text);
    return;
  }
  if (text.startsWith('/img') || text.startsWith('/image')) {
    await handleImageCommand(chatId, text.replace(/^\/(img|image)\s*/i, '').trim());
    return;
  }
  if (text.startsWith('/sticker')) {
    await handleStickerCommand(chatId, text.replace(/^\/sticker\s*/i, '').trim());
    return;
  }
  if (text.startsWith('/voice')) {
    await handleVoiceCommand(chatId, text.replace(/^\/voice\s*/i, '').trim());
    return;
  }

  if (busy.get(chatId)) {
    await tg.sendMessage(chatId, 'Ещё думаю над предыдущим сообщением — секунду.');
    return;
  }

  const prompt = text.replace(/^\/ask\s+/i, '').trim();
  if (!prompt) {
    await tg.sendMessage(chatId, 'Напиши текст вопроса после /ask.');
    return;
  }

  busy.set(chatId, true);
  const provider = providerFor(chatId);
  console.log(`[msg] chat=${chatId} provider=${provider} chars=${prompt.length}`);
  const typing = setInterval(() => void tg.sendChatAction(chatId), 4500);
  await tg.sendChatAction(chatId);

  try {
    const messages = [...(history.get(chatId) ?? []), { role: 'user', content: prompt }];
    const { answer, provider: used } = await askWithFallback(provider, messages);

    for (const chunk of splitMessage(answer)) {
      await tg.sendMessage(chatId, chunk);
    }

    const entry = [...messages, { role: 'assistant', content: truncate(answer, 800) }];
    history.set(chatId, entry.slice(-config.historyLimit * 2));
    console.log(`[answer] chat=${chatId} provider=${used} chars=${answer.length}`);
  } catch (error) {
    console.error(`[chat] ${error.message}`);
    await tg.sendMessage(chatId, `Не получилось: ${truncate(error.message, 500)}`);
  } finally {
    clearInterval(typing);
    busy.delete(chatId);
  }
}

async function handleImageCommand(chatId, prompt) {
  if (!prompt) {
    await tg.sendMessage(chatId, 'Формат: /img <описание картинки>');
    return;
  }
  if (busy.get(chatId)) {
    await tg.sendMessage(chatId, 'Сначала дождись предыдущего ответа.');
    return;
  }

  busy.set(chatId, true);
  console.log(`[img] chat=${chatId} chars=${prompt.length}`);
  await tg.sendChatAction(chatId, 'upload_photo');

  try {
    const { buffer, contentType, extension } = await generateImage({
      prompt,
      model: config.imageModel,
    });
    await tg.sendPhoto(chatId, {
      buffer,
      contentType,
      filename: `lyra.${extension}`,
      caption: truncate(prompt, 900),
    });
    console.log(`[img] chat=${chatId} bytes=${buffer.length}`);
  } catch (error) {
    console.error(`[img] ${error.message}`);
    await tg.sendMessage(chatId, `Картинка не получилась: ${truncate(error.message, 400)}`);
  } finally {
    busy.delete(chatId);
  }
}

async function handleStickerCommand(chatId, prompt) {
  if (!prompt) {
    await tg.sendMessage(chatId, 'Формат: /sticker <описание>');
    return;
  }
  if (busy.get(chatId)) {
    await tg.sendMessage(chatId, 'Сначала дождись предыдущего ответа.');
    return;
  }

  busy.set(chatId, true);
  console.log(`[sticker] chat=${chatId} chars=${prompt.length}`);
  await tg.sendChatAction(chatId, 'choose_sticker');

  try {
    const webp = await makeSticker({ prompt });
    await tg.sendSticker(chatId, { buffer: webp, emoji: '🙂' });
    console.log(`[sticker] chat=${chatId} bytes=${webp.length}`);
  } catch (error) {
    console.error(`[sticker] ${error.message}`);
    await tg.sendMessage(chatId, `Стикер не получился: ${truncate(error.message, 400)}`);
  } finally {
    busy.delete(chatId);
  }
}

async function handleVoiceCommand(chatId, text) {
  if (!text) {
    await tg.sendMessage(chatId, 'Формат: /voice <текст для озвучки>');
    return;
  }
  if (busy.get(chatId)) {
    await tg.sendMessage(chatId, 'Сначала дождись предыдущего ответа.');
    return;
  }

  busy.set(chatId, true);
  console.log(`[voice] chat=${chatId} chars=${text.length}`);
  await tg.sendChatAction(chatId, 'record_voice');

  try {
    const ogg = await textToSpeech(text);
    await tg.sendVoice(chatId, { buffer: ogg });
    console.log(`[voice] chat=${chatId} bytes=${ogg.length}`);
  } catch (error) {
    console.error(`[voice] ${error.message}`);
    await tg.sendMessage(chatId, `Озвучка не получилась: ${truncate(error.message, 400)}`);
  } finally {
    busy.delete(chatId);
  }
}

/** Incoming voice message, video note or audio file: transcribe it and answer. */
async function handleAudioMessage(chatId, audio, message) {
  if (busy.get(chatId)) {
    await tg.sendMessage(chatId, 'Ещё работаю над предыдущим сообщением — секунду.');
    return;
  }

  busy.set(chatId, true);
  const label = message.video_note ? 'видеокружок' : 'голосовое';
  console.log(`[audio] chat=${chatId} kind=${label} bytes=${audio.file_size ?? '?'}`);
  const typing = setInterval(() => void tg.sendChatAction(chatId), 4500);
  await tg.sendChatAction(chatId, 'typing');

  try {
    const filePath = await tg.getFile(audio.file_id);
    if (!filePath) throw new Error('Telegram не вернул путь к файлу.');
    const buffer = await tg.downloadFile(filePath);
    const extension = filePath.split('.').pop()?.toLowerCase() || 'ogg';
    const transcript = await speechToText(buffer, { inputExt: extension });
    await tg.sendMessage(chatId, `🎧 «${truncate(transcript, 900)}»`);

    const provider = providerFor(chatId);
    const messages = [...(history.get(chatId) ?? []), { role: 'user', content: transcript }];
    const { answer } = await askWithFallback(provider, messages);

    for (const chunk of splitMessage(answer)) {
      await tg.sendMessage(chatId, chunk);
    }
    history.set(chatId, [...messages, { role: 'assistant', content: truncate(answer, 800) }].slice(-config.historyLimit * 2));

    if (answer.length <= 600) {
      try {
        const ogg = await textToSpeech(answer);
        await tg.sendVoice(chatId, { buffer: ogg });
      } catch (error) {
        console.warn(`[audio] voice reply skipped: ${error.message}`);
      }
    }
  } catch (error) {
    console.error(`[audio] ${error.message}`);
    await tg.sendMessage(chatId, `Не смог разобрать ${label}: ${truncate(error.message, 400)}`);
  } finally {
    clearInterval(typing);
    busy.delete(chatId);
  }
}

async function handleModelCommand(chatId, text) {
  const [, requested] = text.split(/\s+/, 2);
  const list = availableProviders();

  if (!requested) {
    const current = providerFor(chatId);
    const lines = list.map((item) => `${item.name === current ? '→' : ' '} ${item.name} — ${item.label}`);
    await tg.sendMessage(chatId, [`Текущая модель: ${current}`, '', ...lines, '', 'Сменить: /model <имя>'].join('\n'));
    return;
  }

  if (!PROVIDERS[requested]) {
    await tg.sendMessage(chatId, `Неизвестная модель: ${requested}. Список: /model`);
    return;
  }
  if (!list.some((item) => item.name === requested)) {
    const keyEnv = PROVIDERS[requested].keyEnv;
    await tg.sendMessage(chatId, `Модель ${requested} недоступна: не задан ${keyEnv} в .env.`);
    return;
  }

  providers.set(chatId, requested);
  history.delete(chatId);
  await tg.sendMessage(chatId, `Переключился на ${requested}. Контекст сброшен.`);
}

function providerFor(chatId) {
  const chosen = providers.get(chatId) ?? config.defaultProvider;
  if (!PROVIDERS[chosen]) return 'agent';
  if (chosen === 'agent' && !agentAvailable()) {
    return availableProviders().find((item) => item.kind !== 'agent')?.name ?? 'agent';
  }
  return chosen;
}

/**
 * Ask the selected provider; if it fails, try the other API providers in order.
 * The local agent is never used as a silent fallback: it has different abilities.
 */
async function askWithFallback(provider, messages) {
  const chain = [provider];
  for (const item of availableProviders()) {
    if (item.kind !== 'agent' && item.name !== provider) chain.push(item.name);
  }

  let lastError;
  for (const name of chain) {
    try {
      const answer = await runChat({
        provider: name,
        messages,
        system: SYSTEM_PROMPT,
        agentRunner: (agentPrompt) =>
          askAgent({ prompt: agentPrompt, workspace: config.workspace, timeoutMs: config.agentTimeoutMs }),
      });
      if (name !== provider) console.warn(`[fallback] ${provider} -> ${name}`);
      return { answer, provider: name };
    } catch (error) {
      lastError = error;
      console.warn(`[fail] provider=${name}: ${error.message}`);
    }
  }
  throw lastError;
}

function helpText() {
  const list = availableProviders()
    .map((item) => `/model ${item.name} — ${item.label}`)
    .join('\n');
  return [
    'Lyra AI на связи.',
    '',
    'Просто напиши сообщение — отвечу выбранной моделью.',
    'Можно прислать голосовое или видеокружок — распознаю и отвечу.',
    '',
    '/img <описание> — сгенерировать картинку',
    '/sticker <описание> — сгенерировать стикер',
    '/voice <текст> — озвучить текст',
    '/model — список моделей и текущая',
    '/reset — очистить контекст диалога',
    '',
    list,
  ].join('\n');
}

function loadOffset() {
  try {
    return Number(JSON.parse(readFileSync(offsetFile, 'utf8')).offset) || 0;
  } catch {
    return 0;
  }
}

function saveOffset(value) {
  try {
    writeFileSync(offsetFile, JSON.stringify({ offset: value }), 'utf8');
  } catch (error) {
    console.error(`[state] ${error.message}`);
  }
}

function die(message) {
  console.error(message);
  process.exit(1);
}

process.on('SIGINT', () => {
  console.log('\nОстановлено.');
  process.exit(0);
});
