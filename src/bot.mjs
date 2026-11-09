import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadConfig } from './config.mjs';
import { Telegram, sleep, splitMessage, truncate } from './telegram.mjs';
import { askAgent, describeLauncher } from './agent.mjs';

const config = loadConfig();
const stateDir = join(config.root, 'data');
mkdirSync(stateDir, { recursive: true });
const offsetFile = join(stateDir, 'offset.json');

if (!config.botToken) die('TELEGRAM_BOT_TOKEN не задан. Впиши токен от @BotFather в .env.');
if (!config.deepseekKey) die('DEEPSEEK_API_KEY не задан. Впиши ключ с platform.deepseek.com в .env.');
// The headless agent inherits our environment, so expose the key to the child process.
process.env.DEEPSEEK_API_KEY = config.deepseekKey;

const tg = new Telegram({ token: config.botToken, apiBase: config.apiBase });
const history = new Map(); // chatId -> [{ role: 'user' | 'assistant', text }]
const busy = new Map(); // chatId -> true while an answer is being produced
let offset = loadOffset();

if (config.proxy) {
  console.warn(
    `[warn] TELEGRAM_PROXY=${config.proxy} задан, но fetch учитывает прокси только через ` +
      'NODE_USE_ENV_PROXY=1 / --use-env-proxy. Включай это в run.cmd или используй системный VPN.',
  );
}

console.log(`Lyra AI bot запущен. dsh: ${describeLauncher()}`);
console.log(`Рабочая папка агента: ${config.workspace}`);
// Non-blocking identity check: a blocked or slow network must not delay polling.
const probe = new Telegram({ token: config.botToken, apiBase: config.apiBase, requestTimeoutMs: 15_000 });
probe
  .call('getMe', {}, { retries: 0 })
  .then((me) => console.log(`Карточка бота: @${me?.username ?? '?'}`))
  .catch((error) => console.error(`[getMe] ${error.message}`));

void poll();

async function poll() {
  let failures = 0;
  for (;;) {
    try {
      const updates = await tg.getUpdates(offset, 50);
      failures = 0;
      for (const update of updates ?? []) {
        offset = update.update_id + 1;
        saveOffset(offset);
        void handleUpdate(update);
      }
    } catch (error) {
      failures += 1;
      console.error(`[poll] ${error.message}`);
      if (/401/.test(error.message)) process.exit(1);
      // Back off: Telegram may be unreachable (blocked network) — keep trying quietly.
      await sleep(Math.min(2000 * failures, 30_000));
    }
  }
}

async function handleUpdate(update) {
  const message = update.message;
  const chatId = message?.chat?.id;
  const text = message?.text?.trim();
  if (!chatId || !text) return;

  if (text === '/start' || text === '/help') {
    await tg.sendMessage(chatId, HELP_TEXT);
    return;
  }
  if (text === '/reset') {
    history.delete(chatId);
    await tg.sendMessage(chatId, 'Контекст очищен.');
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
  console.log(`[msg] chat=${chatId} chars=${prompt.length}`);
  const typing = setInterval(() => void tg.sendChatAction(chatId), 4500);
  await tg.sendChatAction(chatId);

  try {
    const { text: answer } = await askAgent({
      prompt: buildPrompt(chatId, prompt),
      workspace: config.workspace,
      timeoutMs: config.agentTimeoutMs,
    });
    console.log(`[answer] chat=${chatId} chars=${answer.length}`);

    for (const chunk of splitMessage(answer)) {
      await tg.sendMessage(chatId, chunk);
    }

    const entry = history.get(chatId) ?? [];
    entry.push({ role: 'user', text: prompt }, { role: 'assistant', text: truncate(answer, 600) });
    history.set(chatId, entry.slice(-config.historyLimit * 2));
  } catch (error) {
    console.error(`[agent] ${error.message}`);
    await tg.sendMessage(chatId, `Не получилось: ${truncate(error.message, 500)}`);
  } finally {
    clearInterval(typing);
    busy.delete(chatId);
  }
}

/** Give the agent the recent dialogue so a chat feels continuous despite one-shot runs. */
function buildPrompt(chatId, text) {
  const entry = history.get(chatId) ?? [];
  if (entry.length === 0) {
    return `${text}\n\nОтвечай по-русски, кратко и по делу — это сообщение в Telegram.`;
  }
  const context = entry
    .map((item) => `${item.role === 'user' ? 'Пользователь' : 'Ты'}: ${item.text}`)
    .join('\n');
  return `Предыдущий диалог:\n${context}\n\nНовое сообщение пользователя: ${text}\n\nОтвечай по-русски, кратко и по делу — это сообщение в Telegram.`;
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

const HELP_TEXT = [
  'Lyra AI на связи.',
  '',
  'Напиши вопрос — передам его агенту DeepSeek Harness, у которого есть доступ к файлам и терминалу в рабочей папке.',
  '',
  '/ask <текст> — явно задать вопрос агенту',
  '/reset — очистить контекст диалога',
  '/help — это сообщение',
].join('\n');

process.on('SIGINT', () => {
  console.log('\nОстановлено.');
  process.exit(0);
});
