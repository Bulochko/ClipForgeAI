import { createServer } from 'node:http';

/**
 * Minimal webhook receiver for Telegram updates.
 * Telegram requires HTTPS, so this listens on plain HTTP behind a TLS terminator
 * (Caddy, nginx or a platform edge). The shared secret header guards the endpoint.
 */
export function startWebhookServer({ port, secret, onUpdate, path = '/telegram', host = '0.0.0.0' }) {
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

    // Acknowledge immediately: Telegram retries anything slower than ~60s.
    response.writeHead(200, { 'content-type': 'text/plain' });
    response.end('ok');

    try {
      const update = JSON.parse(body);
      void onUpdate(update);
    } catch (error) {
      console.error(`[webhook] ${error.message}`);
    }
  });

  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, host, () => resolve(server));
  });
}
