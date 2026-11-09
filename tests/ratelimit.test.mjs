import test from 'node:test';
import assert from 'node:assert/strict';

import { createLimiter } from '../src/ratelimit.mjs';

test('limiter allows requests up to the limit', () => {
  const limiter = createLimiter({ limit: 3, windowMs: 60_000 });
  const start = 1_000_000;

  assert.equal(limiter.allow('chat', start), true);
  assert.equal(limiter.allow('chat', start + 1), true);
  assert.equal(limiter.allow('chat', start + 2), true);
  assert.equal(limiter.allow('chat', start + 3), false);
});

test('limiter frees slots as the window slides', () => {
  const limiter = createLimiter({ limit: 2, windowMs: 10_000 });
  const start = 5_000_000;

  assert.equal(limiter.allow('chat', start), true);
  assert.equal(limiter.allow('chat', start + 1_000), true);
  assert.equal(limiter.allow('chat', start + 2_000), false);
  assert.equal(limiter.allow('chat', start + 11_000), true);
});

test('limiter keeps chats independent and reports retry delay', () => {
  const limiter = createLimiter({ limit: 1, windowMs: 30_000 });
  const start = 9_000_000;

  assert.equal(limiter.allow('a', start), true);
  assert.equal(limiter.allow('b', start), true);
  assert.equal(limiter.allow('a', start + 1_000), false);
  const wait = limiter.retryAfter('a', start + 1_000);
  assert.ok(wait >= 1 && wait <= 29, `unexpected wait: ${wait}`);
});

test('limit of zero disables throttling', () => {
  const limiter = createLimiter({ limit: 0, windowMs: 60_000 });
  for (let index = 0; index < 50; index += 1) {
    assert.equal(limiter.allow('chat', index), true);
  }
});
