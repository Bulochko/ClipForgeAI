import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));

/** Minimal .env reader: KEY=VALUE lines, # comments, optional quotes. */
function readEnvFile(path) {
  if (!existsSync(path)) return {};
  const out = {};
  for (const rawLine of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

let envLoaded = false;

/** Load .env into process.env exactly once; safe to call from any module. */
export function loadEnvOnce() {
  if (envLoaded) return;
  const fileEnv = readEnvFile(join(ROOT, '.env'));
  for (const [key, value] of Object.entries(fileEnv)) {
    if (!process.env[key]) process.env[key] = value;
  }
  envLoaded = true;
}

export function loadConfig() {
  loadEnvOnce();
  const pick = (name) => (process.env[name] ?? '').trim();
  const rateLimitRaw = pick('RATE_LIMIT_PER_MIN');
  const rateLimitNumber = Number(rateLimitRaw);

  return {
    root: ROOT,
    botToken: pick('TELEGRAM_BOT_TOKEN'),
    deepseekKey: pick('DEEPSEEK_API_KEY'),
    proxy: pick('TELEGRAM_PROXY'),
    apiBase: pick('TELEGRAM_API_BASE') || 'https://api.telegram.org',
    // Where the agent runs. Defaults to the repository root.
    workspace: pick('AGENT_WORKSPACE') || ROOT,
    agentTimeoutMs: Number(pick('AGENT_TIMEOUT_MS')) || 180_000,
    historyLimit: Number(pick('HISTORY_LIMIT')) || 8,
    defaultProvider: pick('DEFAULT_PROVIDER') || 'agent',
    imageModel: pick('IMAGE_MODEL') || 'flux',
    mode: (pick('MODE') || 'polling').toLowerCase(),
    webhookUrl: pick('WEBHOOK_URL'),
    webhookPort: Number(pick('WEBHOOK_PORT')) || 8443,
    webhookSecret: pick('WEBHOOK_SECRET'),
    // Empty list is private by default: only /start, /help and /id are allowed for setup.
    allowedChatIds: pick('ALLOWED_CHAT_IDS')
      .split(',')
      .map((value) => Number(value.trim()))
      .filter((value) => Number.isSafeInteger(value) && value !== 0),
    allowPublicChats: pick('ALLOW_PUBLIC_CHATS').toLowerCase() === 'true',
    rateLimitPerMin: rateLimitRaw === ''
      ? 12
      : Number.isFinite(rateLimitNumber) ? Math.max(0, Math.floor(rateLimitNumber)) : 12,
  };
}

export { ROOT };
