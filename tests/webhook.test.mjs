import test from 'node:test';
import assert from 'node:assert/strict';

import { startWebhookServer } from '../src/webhook.mjs';

test('webhook refuses to start without a valid secret', () => {
  assert.throws(
    () => startWebhookServer({ port: 0, secret: '', onUpdate: () => {} }),
    /secret/i,
  );
  assert.throws(
    () => startWebhookServer({ port: 0, secret: 'contains spaces', onUpdate: () => {} }),
    /secret/i,
  );
});

test('webhook requires an update handler', () => {
  assert.throws(
    () => startWebhookServer({ port: 0, secret: 'valid_secret-123', onUpdate: null }),
    /onUpdate/i,
  );
});
