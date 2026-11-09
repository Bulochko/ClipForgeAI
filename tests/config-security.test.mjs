import test from 'node:test';
import assert from 'node:assert/strict';

import { isChatAllowed, loadConfig } from '../src/config.mjs';

test('empty allowlist denies normal messages but permits setup commands', () => {
  const policy = { allowedChatIds: [], allowPublicChats: false };

  assert.equal(isChatAllowed({ ...policy, chatId: 123, text: 'Привет' }), false);
  assert.equal(isChatAllowed({ ...policy, chatId: 123, text: '/start' }), true);
  assert.equal(isChatAllowed({ ...policy, chatId: 123, text: '/id' }), true);
  assert.equal(isChatAllowed({ ...policy, chatId: 123, text: '/id@LyraBot' }), true);
  assert.equal(isChatAllowed({ ...policy, chatId: 123, text: '/model gemini' }), false);
});

test('allowlist permits only listed chat IDs', () => {
  const policy = { allowedChatIds: [123, -456], allowPublicChats: false };

  assert.equal(isChatAllowed({ ...policy, chatId: 123, text: 'hello' }), true);
  assert.equal(isChatAllowed({ ...policy, chatId: -456, text: 'hello' }), true);
  assert.equal(isChatAllowed({ ...policy, chatId: 999, text: '/start' }), false);
});

test('public access requires an explicit opt-in and overrides an allowlist', () => {
  assert.equal(isChatAllowed({
    chatId: 999,
    allowedChatIds: [],
    allowPublicChats: true,
    text: 'hello',
  }), true);
  assert.equal(isChatAllowed({
    chatId: 999,
    allowedChatIds: [123],
    allowPublicChats: true,
    text: 'hello',
  }), true);
});

test('rate limit zero is preserved as disabled', () => {
  const original = process.env.RATE_LIMIT_PER_MIN;
  process.env.RATE_LIMIT_PER_MIN = '0';
  try {
    assert.equal(loadConfig().rateLimitPerMin, 0);
  } finally {
    if (original === undefined) delete process.env.RATE_LIMIT_PER_MIN;
    else process.env.RATE_LIMIT_PER_MIN = original;
  }
});
