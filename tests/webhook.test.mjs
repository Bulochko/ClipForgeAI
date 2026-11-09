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

test('webhook acknowledges only after the update is durably accepted', async () => {
  let accepted = false;
  const server = await startWebhookServer({
    port: 0,
    secret: 'valid_secret-123',
    onUpdate: async (update) => {
      await new Promise((resolve) => setTimeout(resolve, 25));
      accepted = update.update_id === 42;
    },
  });

  try {
    const address = server.address();
    const response = await fetch(`http://127.0.0.1:${address.port}/telegram`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-telegram-bot-api-secret-token': 'valid_secret-123',
      },
      body: JSON.stringify({ update_id: 42 }),
    });

    assert.equal(response.status, 200);
    assert.equal(accepted, true);
  } finally {
    await new Promise((resolve, reject) => {
      server.close((error) => error ? reject(error) : resolve());
    });
  }
});

test('webhook returns 500 when update persistence fails', async () => {
  const server = await startWebhookServer({
    port: 0,
    secret: 'valid_secret-123',
    onUpdate: async () => {
      throw new Error('disk unavailable');
    },
  });

  try {
    const address = server.address();
    const response = await fetch(`http://127.0.0.1:${address.port}/telegram`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-telegram-bot-api-secret-token': 'valid_secret-123',
      },
      body: JSON.stringify({ update_id: 43 }),
    });

    assert.equal(response.status, 500);
  } finally {
    await new Promise((resolve, reject) => {
      server.close((error) => error ? reject(error) : resolve());
    });
  }
});
