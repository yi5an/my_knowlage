# X web collector: Playwright + Chromium with a virtual display.
#
# X started rejecting headless Chromium fingerprints around 2026-07-17, so on
# servers without a display the collector runs headful inside xvfb. x.com is
# not reachable directly from CN cloud networks; route the browser through the
# mihomo proxy via X_COLLECTOR_PROXY_SERVER.
FROM mcr.microsoft.com/playwright:v1.61.1-noble

RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Backend on the compose network; override per deployment as needed.
ENV KNOWPILOT_URL=http://backend:8010 \
    X_COLLECTOR_ID=prod-server

# Start Xvfb explicitly (xvfb-run's wrapper kills the node child in
# containers); clean stale locks from a previous container restart first.
CMD ["sh", "-c", "rm -f /tmp/.X99-lock /tmp/.X11-unix/X99; Xvfb :99 -screen 0 1280x800x24 -nolisten tcp & sleep 1; DISPLAY=:99 exec node dist/cli.js run"]
