import { createServer } from 'node:http';

/**
 * Minimal webhook receiver for Telegram updates.
 * Telegram requires HTTPS, so this listens on plain HTTP behind a TLS terminator
 * (Caddy, nginx or a platform edge). The shared secret header guards the endpoint.
 */
export function startWebhookServer({ port, secret, onUpdate, path = '/telegram', host = '0.0.0.0' }) {
  if (typeof secret !== 'string' || !/^[A-Za-z0-9_-]{1,256}$/.test(secret)) {
    throw new Error('A valid Telegram webhook secret is required.');
  }
  if (typeof onUpdate !== 'function') {
    throw new TypeError('onUpdate must be a function.');
  }

  const server = createServer(async (request, response) => {
    if (request.method === 'GET') {
      const isHealth = request.url === '/health';
      response.writeHead(200, { 'content-type': isHealth ? 'application/json' : 'text/plain' });
      response.end(
        isHealth ? JSON.stringify({ ok: true, uptime: Math.round(process.uptime()) }) : 'ok',
      );
      return;
    }
    if (request.method !== 'POST' || request.url !== path) {
      response.writeHead(404, { 'content-type': 'text/plain' });
      response.end('not found');
      return;
    }
    if (secret && request.headers['x-telegram-bot-api-secret-token'] !== secret) {
      response.writeHead(401, { 'content-type': 'text/plain' });
      response.end('unauthorized');
      return;
    }

    let body = '';
    for await (const chunk of request) {
      body += chunk;
      if (body.length > 2_000_000) {
        response.writeHead(413);
        response.end();
        return;
      }
    }

    let update;
    try {
      update = JSON.parse(body);
    } catch (error) {
      response.writeHead(400, { 'content-type': 'text/plain' });
      response.end('invalid JSON');
      return;
    }

    // Acknowledge quickly; the persistent Node process continues handling the update.
    response.writeHead(200, { 'content-type': 'text/plain' });
    response.end('ok');

    Promise.resolve()
      .then(() => onUpdate(update))
      .catch((error) => console.error(`[webhook] ${error?.message ?? error}`));
  });

  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, host, () => resolve(server));
  });
}
