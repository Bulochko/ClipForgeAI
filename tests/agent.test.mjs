import test from 'node:test';
import assert from 'node:assert/strict';

import { createAgentEnv } from '../src/agent.mjs';

test('local agent receives only its runtime variables and DeepSeek credential', () => {
  const env = createAgentEnv({
    PATH: '/usr/bin',
    HOME: '/home/test',
    DEEPSEEK_API_KEY: 'deepseek-test-key',
    TELEGRAM_BOT_TOKEN: 'telegram-secret',
    GEMINI_API_KEY: 'gemini-secret',
    GROQ_API_KEY: 'groq-secret',
    OPENROUTER_API_KEY: 'openrouter-secret',
    POLLINATIONS_API_KEY: 'pollinations-secret',
  });

  assert.equal(env.PATH, '/usr/bin');
  assert.equal(env.HOME, '/home/test');
  assert.equal(env.DEEPSEEK_API_KEY, 'deepseek-test-key');
  assert.equal('TELEGRAM_BOT_TOKEN' in env, false);
  assert.equal('GEMINI_API_KEY' in env, false);
  assert.equal('GROQ_API_KEY' in env, false);
  assert.equal('OPENROUTER_API_KEY' in env, false);
  assert.equal('POLLINATIONS_API_KEY' in env, false);
});

test('Electron launcher receives its required runtime flag', () => {
  const env = createAgentEnv({ PATH: '/usr/bin' }, { electron: true });
  assert.equal(env.ELECTRON_RUN_AS_NODE, '1');
});
