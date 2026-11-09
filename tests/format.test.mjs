import test from 'node:test';
import assert from 'node:assert/strict';

import { splitMessage, truncate } from '../src/telegram.mjs';
import { splitForTts } from '../src/speech.mjs';
import { loadConfig } from '../src/config.mjs';

test('truncate keeps short text intact and cuts long text', () => {
  assert.equal(truncate('привет', 10), 'привет');
  const cut = truncate('a'.repeat(50), 10);
  assert.equal(cut.length, 10);
  assert.ok(cut.endsWith('…'));
});

test('splitMessage leaves short answers as one chunk', () => {
  assert.deepEqual(splitMessage('короткий ответ'), ['короткий ответ']);
});

test('splitMessage breaks long answers within the Telegram limit', () => {
  const paragraph = 'Это предложение для проверки разбиения. ';
  const text = paragraph.repeat(400);
  const chunks = splitMessage(text, 4000);

  assert.ok(chunks.length > 1);
  for (const chunk of chunks) {
    assert.ok(chunk.length <= 4000, `chunk too long: ${chunk.length}`);
    assert.ok(chunk.length > 0);
  }
  const joined = chunks.join(' ').replace(/\s+/g, ' ').trim();
  assert.equal(joined, text.replace(/\s+/g, ' ').trim());
});

test('splitForTts keeps every chunk within the translate limit', () => {
  const text = 'Первое предложение. Второе предложение тоже есть! И третье — с тире, вопросом и ответом?';
  const chunks = splitForTts(text);

  assert.ok(chunks.length >= 1);
  for (const chunk of chunks) {
    assert.ok(chunk.length <= 180, `chunk too long: ${chunk.length}`);
  }
  assert.equal(chunks.join(' ').replace(/\s+/g, ' '), text.replace(/\s+/g, ' '));
});

test('config reads booleans and lists from env with sane defaults', () => {
  const config = loadConfig();
  assert.ok(Number.isFinite(config.historyLimit));
  assert.ok(Array.isArray(config.allowedChatIds));
  assert.ok(['polling', 'webhook'].includes(config.mode));
  assert.ok(config.root.endsWith('Lyra-AI'));
});
