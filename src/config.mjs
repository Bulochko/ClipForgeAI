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

export function loadConfig() {
  const fileEnv = readEnvFile(join(ROOT, '.env'));
  // Expose every .env entry to process.env so provider modules see the same keys.
  for (const [key, value] of Object.entries(fileEnv)) {
    if (!process.env[key]) process.env[key] = value;
  }
  const pick = (name) => (process.env[name] ?? fileEnv[name] ?? '').trim();

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
  };
}

export { ROOT };
