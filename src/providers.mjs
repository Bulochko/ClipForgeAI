/**
 * Provider registry: one place that knows how to talk to each LLM backend.
 * All of them are optional — a provider is usable only when its key is present.
 */
import { agentAvailable } from './agent.mjs';

export const PROVIDERS = {
  agent: {
    kind: 'agent',
    label: 'DSH-агент (файлы и терминал на этом ПК)',
    keyEnv: null,
  },
  gemini: {
    kind: 'gemini',
    label: 'Google Gemini (бесплатный тир)',
    model: 'gemini-2.5-flash',
    keyEnv: 'GEMINI_API_KEY',
  },
  groq: {
    kind: 'openai',
    label: 'Groq / Llama (бесплатный тир)',
    baseUrl: 'https://api.groq.com/openai/v1',
    model: 'llama-3.3-70b-versatile',
    keyEnv: 'GROQ_API_KEY',
  },
  openrouter: {
    kind: 'openai',
    label: 'OpenRouter (бесплатные модели)',
    baseUrl: 'https://openrouter.ai/api/v1',
    model: 'meta-llama/llama-3.3-70b-instruct:free',
    keyEnv: 'OPENROUTER_API_KEY',
  },
  deepseek: {
    kind: 'openai',
    label: 'DeepSeek API (платный, дешёвый)',
    baseUrl: 'https://api.deepseek.com/v1',
    model: 'deepseek-chat',
    keyEnv: 'DEEPSEEK_API_KEY',
  },
};

export function providerKey(provider) {
  const config = PROVIDERS[provider];
  if (!config) throw new Error(`Неизвестный провайдер: ${provider}`);
  return config.keyEnv ? (process.env[config.keyEnv] ?? '').trim() : '';
}

export function availableProviders() {
  return Object.entries(PROVIDERS)
    .filter(([name, config]) => (name === 'agent' ? agentAvailable() : Boolean(providerKey(name))))
    .map(([name, config]) => ({ name, ...config }));
}

/**
 * Send a chat request to the given provider.
 * `messages` is [{ role: 'user' | 'assistant', content: string }, ...]
 */
export async function chat({ provider = 'agent', messages, system, agentRunner }) {
  const config = PROVIDERS[provider];
  if (!config) throw new Error(`Неизвестный провайдер: ${provider}`);

  if (config.kind === 'agent') {
    if (!agentAvailable()) {
      throw new Error('Режим агента доступен только на ПК с установленным DeepSeek Harness.');
    }
    if (!agentRunner) throw new Error('Режим агента недоступен в этой сборке.');
    const prompt = renderPrompt(messages, system);
    const { text } = await agentRunner(prompt);
    return text;
  }

  const key = providerKey(provider);
  if (!key) throw new Error(`Для ${provider} не задан ключ ${config.keyEnv}. Добавь его в .env.`);

  const model = (process.env[`${provider.toUpperCase()}_MODEL`] ?? '').trim() || config.model;
  return config.kind === 'gemini'
    ? geminiChat({ key, model, messages, system })
    : openAiChat({ key, baseUrl: config.baseUrl, model, messages, system });
}

function renderPrompt(messages, system) {
  const history = messages
    .map((message) => `${message.role === 'user' ? 'Пользователь' : 'Ты'}: ${message.content}`)
    .join('\n');
  return [system, history].filter(Boolean).join('\n\n');
}

async function openAiChat({ key, baseUrl, model, messages, system }) {
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${key}`,
    },
    body: JSON.stringify({
      model,
      messages: [...(system ? [{ role: 'system', content: system }] : []), ...messages],
      temperature: 0.7,
    }),
    signal: AbortSignal.timeout(120_000),
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(`${model}: HTTP ${response.status} ${payload?.error?.message ?? ''}`.trim());
  }
  const text = payload?.choices?.[0]?.message?.content;
  if (!text) throw new Error(`${model}: пустой ответ`);
  return text.trim();
}

async function geminiChat({ key, model, messages, system }) {
  const contents = messages.map((message) => ({
    role: message.role === 'assistant' ? 'model' : 'user',
    parts: [{ text: message.content }],
  }));

  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(key)}`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        ...(system ? { systemInstruction: { parts: [{ text: system }] } } : {}),
        contents,
      }),
      signal: AbortSignal.timeout(120_000),
    },
  );

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(`${model}: HTTP ${response.status} ${payload?.error?.message ?? ''}`.trim());
  }
  const parts = payload?.candidates?.[0]?.content?.parts ?? [];
  const text = parts.map((part) => part.text).filter(Boolean).join('\n').trim();
  if (!text) throw new Error(`${model}: пустой ответ`);
  return text;
}
