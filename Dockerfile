FROM node:24-slim

# ffmpeg powers voice messages, video notes and stickers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# No npm dependencies: the bot only uses Node built-ins.
COPY package.json ./
COPY src ./src

ENV NODE_ENV=production
ENV MODE=webhook
ENV WEBHOOK_PORT=8443

EXPOSE 8443

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["node", "src/bot.mjs"]
