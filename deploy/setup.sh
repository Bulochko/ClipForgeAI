#!/usr/bin/env bash
# Provision Lyra AI on a fresh Debian/Ubuntu VPS.
# Usage: sudo bash deploy/setup.sh [domain]
#   domain — optional; enables webhook mode through Caddy with automatic TLS.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Bulochko/Lyra-AI.git}"
APP_DIR="${APP_DIR:-/opt/lyra-ai}"
DOMAIN="${1:-}"

if [[ ${EUID} -ne 0 ]]; then
  echo "Запусти от root: sudo bash deploy/setup.sh [domain]" >&2
  exit 1
fi

echo "== пакеты =="
apt-get update -y
apt-get install -y git ffmpeg curl ca-certificates gpg

NODE_MAJOR="$(node -v 2>/dev/null | sed 's/^v\([0-9]*\).*/\1/' || echo 0)"
if [[ "${NODE_MAJOR:-0}" -lt 20 ]]; then
  echo "== node 22 из NodeSource =="
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

echo "== пользователь и код =="
if ! id -u lyra >/dev/null 2>&1; then
  useradd -r -m -d "${APP_DIR}" -s /usr/sbin/nologin lyra
fi

if [[ -d "${APP_DIR}/.git" ]]; then
  runuser -u lyra -- git -C "${APP_DIR}" pull --ff-only
else
  mkdir -p "${APP_DIR}"
  chown lyra:lyra "${APP_DIR}"
  runuser -u lyra -- git clone "${REPO_URL}" "${APP_DIR}"
fi

mkdir -p "${APP_DIR}/data"
chown -R lyra:lyra "${APP_DIR}"

if [[ ! -f "${APP_DIR}/.env" ]]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  chown lyra:lyra "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
  echo "!! Заполни ${APP_DIR}/.env (токен, ключи) и запусти скрипт снова."
  exit 0
fi

echo "== systemd =="
install -m 644 "${APP_DIR}/deploy/lyra-ai.service" /etc/systemd/system/lyra-ai.service
systemctl daemon-reload
systemctl enable lyra-ai

if [[ -n "${DOMAIN}" ]]; then
  echo "== caddy для ${DOMAIN} =="
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  if ! command -v caddy >/dev/null; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -y && apt-get install -y caddy
  fi
  sed "s/bot\.example\.com/${DOMAIN}/" "${APP_DIR}/deploy/Caddyfile" > /etc/caddy/Caddyfile
  systemctl reload caddy || systemctl restart caddy
  echo "В .env укажи: MODE=webhook, WEBHOOK_URL=https://${DOMAIN}/telegram"
fi

systemctl restart lyra-ai
sleep 2
systemctl --no-pager --full status lyra-ai || true

echo "== проверка окружения =="
runuser -u lyra -- bash -lc "cd '${APP_DIR}' && node src/doctor.mjs --deep" || true

echo "Логи: journalctl -u lyra-ai -f"
