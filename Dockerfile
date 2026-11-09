FROM node:24-slim

# ffmpeg powers voice messages, video notes and stickers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# No npm dependencies: the bot only uses Node built-ins.
COPY --chown=node:node package.json ./
COPY --chown=node:node src ./src

# The bot only needs write access to its runtime data directory.
RUN mkdir -p /app/data && chown -R node:node /app
USER node

ENV NODE_ENV=production
ENV MODE=webhook
ENV WEBHOOK_PORT=8443

EXPOSE 8443

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:'+(process.env.WEBHOOK_PORT||8443)+'/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["node", "src/bot.mjs"]
