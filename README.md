# Lyra AI

Telegram-ассистент с мостом к DeepSeek Harness: сообщение из Telegram превращается
в один запуск агента (`dsh headless`), ответ возвращается в чат. У агента есть доступ
к файлам и терминалу в рабочей папке.

## Как это работает

```
Telegram  ──►  bot.mjs  ──►  dsh headless "<промпт>"  ──►  ответ  ──►  Telegram
```

- `src/config.mjs` — читает `.env`, без внешних зависимостей.
- `src/telegram.mjs` — клиент Bot API на `fetch`: long polling, повторы, разбивка длинных ответов.
- `src/agent.mjs` — запуск `dsh headless` с таймаутом и очисткой служебного вывода.
- `src/bot.mjs` — маршрутизация сообщений, контекст диалога, индикатор «печатает».

## Настройка

1. Скопируй `.env.example` в `.env`.
2. `TELEGRAM_BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather).
3. Добавь хотя бы один ключ AI-провайдера: `GEMINI_API_KEY`, `GROQ_API_KEY`,
   `OPENROUTER_API_KEY` или `DEEPSEEK_API_KEY`.
4. Запусти `run.cmd` (использует Node из DeepSeek Harness, ставить ничего не нужно).

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен бота, обязателен |
| `DEEPSEEK_API_KEY` | ключ DeepSeek, обязателен для DeepSeek API |
| `POLLINATIONS_API_KEY` | ключ Pollinations для генерации изображений |
| `TELEGRAM_PROXY` | необязательный прокси (`http://host:port`); включается через `NODE_USE_ENV_PROXY=1` |
| `AGENT_WORKSPACE` | папка, в которой работает агент (по умолчанию корень репозитория) |
| `AGENT_TIMEOUT_MS` | таймаут одного ответа, по умолчанию 180000 |
| `DSH_CLI` | путь к `dsh.cmd`, если установка нестандартная |

## Команды бота

- обычный текст — вопрос выбранной модели;
- `/img <описание>` — генерация картинки через Pollinations (нужен `POLLINATIONS_API_KEY`);
- `/sticker <описание>` — генерация стикера 512×512 WebP;
- `/voice <текст>` — озвучка текста (Gemini TTS, запасной — Google Translate);
- голосовое сообщение, видеокружок или аудио — распознаётся через Gemini
  (`gemini-3.5-transcribe`), при его отсутствии — через Whisper на Groq,
  ответ приходит текстом и коротким голосовым;
- `/model` — список моделей и переключение;
- `/reset` — очистить контекст диалога;
- `/id` — показать chat_id (для `ALLOWED_CHAT_IDS`);
- `/help` — справка.

## Безопасность

По умолчанию доступ закрыт: пока `ALLOWED_CHAT_IDS` пуст, бот отвечает только на
`/start`, `/help` и `/id`, чтобы владелец мог узнать свой chat ID. Добавь полученный
числовой ID в `ALLOWED_CHAT_IDS` (через запятую) и перезапусти бота.
Переменная `ALLOW_PUBLIC_CHATS=true` явно открывает бота всем пользователям;
используй её только осознанно.

`RATE_LIMIT_PER_MIN` (по умолчанию 12) ограничивает число запросов от одного чата в минуту —
это защищает бесплатные квоты моделей от случайного исчерпания. `0` отключает лимит.

## Модели

Провайдеры описаны в `src/providers.mjs`, включаются наличием ключа в `.env`:

| Провайдер | Ключ | Бесплатно |
|---|---|---|
| `agent` | не нужен | локальный агент с файлами и терминалом |
| `gemini` | `GEMINI_API_KEY` | да, free tier |
| `groq` | `GROQ_API_KEY` | тарифы и квоты зависят от плана Groq (+ Whisper) |
| `openrouter` | `OPENROUTER_API_KEY` | да, модели с суффиксом `:free` |
| `deepseek` | `DEEPSEEK_API_KEY` | нет, но дёшево |

Переключение в чате: `/model gemini`. По умолчанию — `DEFAULT_PROVIDER` из `.env`.

## Проверка окружения

```bash
node src/doctor.mjs          # конфигурация, Telegram, ffmpeg, права на запись
node src/doctor.mjs --deep   # плюс живой запрос к каждой модели и генерация картинки
```

Скрипт завершается с кодом 1, если что-то критичное не настроено. На новом сервере
запускай его первым — он же встроен в конец `deploy/setup.sh`.

## Тесты

```bash
npm test
```

Покрывают разбиение длинных ответов, нарезку текста для TTS, конфигурацию и лимитер.

## Требования
- Node из DeepSeek Harness (ставится вместе с приложением) — `run.cmd` использует его сам.
- `ffmpeg` — для голосовых, видеокружков и стикеров. Ставится через
  `winget install Gyan.FFmpeg`; модуль находит его и без обновления PATH.

## Netlify

Текущая конфигурация Netlify публикует только статическую папку `public/`.
Статус Published означает, что опубликована лендинг-страница; он не запускает
`src/bot.mjs` и не поддерживает Telegram-бота как постоянно работающий процесс.
Для самого бота используй VPS через Docker или systemd. Не добавляй Telegram-токен
в клиентскую часть сайта.

## Развёртывание на VPS

Репозиторий приватный. Перед клонированием с VPS создай пользователя и read-only
Deploy key для него:

```bash
sudo useradd -r -m -d /home/lyra -s /usr/sbin/nologin lyra
sudo install -d -o lyra -g lyra -m 700 /home/lyra/.ssh
sudo -u lyra ssh-keygen -t ed25519 -N "" -f /home/lyra/.ssh/id_ed25519
sudo ssh-keyscan github.com | sudo tee /home/lyra/.ssh/known_hosts >/dev/null
sudo chown -R lyra:lyra /home/lyra/.ssh
sudo chmod 600 /home/lyra/.ssh/id_ed25519
sudo cat /home/lyra/.ssh/id_ed25519.pub
```

Добавь выведенный публичный ключ в GitHub → Settings → Deploy keys репозитория
с правом только на чтение. Закрытый ключ остаётся на VPS и не должен попадать
в репозиторий или `.env`.

Два варианта, оба с автоперезапуском.

**Docker (проще)**

```bash
sudo -u lyra git clone git@github.com:Bulochko/Lyra-AI.git /opt/lyra-ai
cd /opt/lyra-ai
sudo -u lyra cp .env.example .env
sudo -u lyra chmod 600 .env
sudo nano .env          # заполнить токен, ключи, WEBHOOK_URL, WEBHOOK_SECRET
sudo docker compose up -d --build
```

**systemd без Docker**

```bash
sudo -u lyra git clone git@github.com:Bulochko/Lyra-AI.git /opt/lyra-ai
cd /opt/lyra-ai
sudo -u lyra cp .env.example .env
sudo -u lyra chmod 600 .env
sudo nano .env
sudo bash deploy/setup.sh
journalctl -u lyra-ai -f
```

Скрипт установит Node.js, ffmpeg, systemd-службу и выполнит проверку окружения.

**Webhook и TLS**

Telegram требует HTTPS, поэтому webhook-порт слушает только localhost, а TLS
терминирует Caddy. Каждый update сначала сохраняется в `data/webhook-queue`, и только
после этого Telegram получает HTTP 200; обработчик разбирает очередь последовательно.
Не удаляй папку `data/` и сохраняй её между перезапусками:

```bash
sudo apt install -y caddy
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile   # заменить домен
sudo systemctl reload caddy
```

В `.env`: `MODE=webhook`, `WEBHOOK_URL=https://bot.example.com/telegram`,
`WEBHOOK_SECRET=<случайная строка из латинских букв, цифр, подчёркивания и дефиса>`. Секрет обязателен.
Без домена оставляй `MODE=polling` — polling
на сервере работает так же надёжно и не требует сертификата.

## Ограничения

- Каждое сообщение — отдельный запуск агента: полноценной сессии нет, контекст
  передаётся последними сообщениями в промпте.
- История диалога и выбранная модель пока хранятся в RAM и сбрасываются при перезапуске.
  Смещение polling и очередь webhook сохраняются в `data/`.
- Локальный DSH-агент работает только на ПК с установленным DeepSeek Harness; на VPS
  используются подключённые API-провайдеры.
- Ответ приходит через 10–60 секунд, в зависимости от задачи.
- Если Telegram недоступен из сети (домены `api.telegram.org` блокируются), нужен
  прокси, VPN или сервер вне блокировки. Без этого long polling не заработает.
