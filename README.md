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
3. `DEEPSEEK_API_KEY` — ключ с [platform.deepseek.com](https://platform.deepseek.com).
4. Запусти `run.cmd` (использует Node из DeepSeek Harness, ставить ничего не нужно).

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен бота, обязателен |
| `DEEPSEEK_API_KEY` | ключ DeepSeek, обязателен |
| `TELEGRAM_PROXY` | необязательный прокси (`http://host:port`); включается через `NODE_USE_ENV_PROXY=1` |
| `AGENT_WORKSPACE` | папка, в которой работает агент (по умолчанию корень репозитория) |
| `AGENT_TIMEOUT_MS` | таймаут одного ответа, по умолчанию 180000 |
| `DSH_CLI` | путь к `dsh.cmd`, если установка нестандартная |

## Команды бота

- обычный текст — вопрос выбранной модели;
- `/img <описание>` — генерация картинки (Pollinations, без ключа);
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

По умолчанию бот отвечает любому, кто его найдёт. Чтобы ограничить доступ, впиши свои
идентификаторы в `ALLOWED_CHAT_IDS` (через запятую, узнать можно командой `/id`).

`RATE_LIMIT_PER_MIN` (по умолчанию 12) ограничивает число запросов от одного чата в минуту —
это защищает бесплатные квоты моделей от случайного исчерпания. `0` отключает лимит.

## Модели

Провайдеры описаны в `src/providers.mjs`, включаются наличием ключа в `.env`:

| Провайдер | Ключ | Бесплатно |
|---|---|---|
| `agent` | не нужен | локальный агент с файлами и терминалом |
| `gemini` | `GEMINI_API_KEY` | да, free tier |
| `groq` | `GROQ_API_KEY` | да, free tier (+ Whisper) |
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
node --test tests/format.test.mjs
```

Покрывают разбиение длинных ответов, нарезку текста для TTS и разбор конфигурации.

## Требования
- Node из DeepSeek Harness (ставится вместе с приложением) — `run.cmd` использует его сам.
- `ffmpeg` — для голосовых, видеокружков и стикеров. Ставится через
  `winget install Gyan.FFmpeg`; модуль находит его и без обновления PATH.

## Развёртывание на VPS

Два варианта, оба с автоперезапуском.

**Docker (проще)**

```bash
git clone https://github.com/Bulochko/Lyra-AI.git /opt/lyra-ai
cd /opt/lyra-ai
cp .env.example .env   # заполнить токен, ключи, WEBHOOK_URL, WEBHOOK_SECRET
docker compose up -d --build
```

**systemd без Docker**

```bash
sudo useradd -r -m -d /opt/lyra-ai lyra
sudo -u lyra git clone https://github.com/Bulochko/Lyra-AI.git /opt/lyra-ai
cd /opt/lyra-ai && cp .env.example .env   # заполнить
sudo apt install -y nodejs ffmpeg
sudo cp deploy/lyra-ai.service /etc/systemd/system/
sudo systemctl enable --now lyra-ai
journalctl -u lyra-ai -f
```

**Webhook и TLS**

Telegram требует HTTPS, поэтому webhook-порт слушает только localhost, а TLS
терминирует Caddy:

```bash
sudo apt install -y caddy
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile   # заменить домен
sudo systemctl reload caddy
```

В `.env`: `MODE=webhook`, `WEBHOOK_URL=https://bot.example.com/telegram`,
`WEBHOOK_SECRET=<случайная строка>`. Без домена оставляй `MODE=polling` — polling
на сервере работает так же надёжно и не требует сертификата.

## Ограничения

- Каждое сообщение — отдельный запуск агента: полноценной сессии нет, контекст
  передаётся последними сообщениями в промпте.
- Ответ приходит через 10–60 секунд, в зависимости от задачи.
- Если Telegram недоступен из сети (домены `api.telegram.org` блокируются), нужен
  прокси, VPN или сервер вне блокировки. Без этого long polling не заработает.
