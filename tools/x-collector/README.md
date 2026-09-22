# X Web Collector

Runs on the production server (Docker service `x-collector` in
`docker-compose.prod.yml`). Nothing runs on dev machines anymore.

## How it works

- Headful Chromium inside the container's Xvfb display (X rejects headless
  fingerprints since 2026-07-17).
- Browser traffic goes through the `mihomo` proxy (`X_COLLECTOR_PROXY_SERVER`).
- Account collection uses the **logged-in persistent profile** (plan A since
  2026-09-22): X removed anonymous GraphQL, so the transport steals
  `authorization` + `x-csrf-token` from the logged-in page's own API requests
  and discovers `UserTweets` / `UserByScreenName` query ids from its bundles.
- Keyword collection uses the same persistent profile.

## Login / re-login (cookie injection)

Cookies expire every few weeks; when collection fails with `auth_required`,
inject fresh cookies into the server profile:

1. In a normal browser logged into x.com, export cookies for `x.com`
   (Cookie-Editor extension → Export → Netscape). The critical ones are
   `auth_token`, `ct0`, `twid`, `guest_id*`, `personalization_id`.
2. Copy the export to the server and inject it into the container profile
   (the CLI command is built into the image):

   ```bash
   # local: send the cookie file
   rsync -az -e "ssh -p 12222" cookies.txt yi5an@123.57.165.38:/tmp/
   # server: inject + verify (expects {"logged_in":true,...})
   docker cp /tmp/cookies.txt knowpilot-x-collector:/tmp/cookies.txt
   docker exec -e DISPLAY=:99 knowpilot-x-collector node dist/cli.js inject-cookies /tmp/cookies.txt
   docker exec knowpilot-x-collector rm /tmp/cookies.txt
   ```

   Expected output ends with `account_switcher: FOUND (logged in)`.
3. Remove the cookie file everywhere after injection. Never commit it.

Notes:

- Do **not** copy the whole browser profile between machines: Chromium
  encrypts cookies with an OS-bound key, so a macOS profile cannot be read on
  Linux (injection is the supported path).
- Interactive login on the server is not possible without a display tunnel;
  cookie injection replaces it.

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `KNOWPILOT_URL` | `http://backend:8010` | Backend base URL |
| `X_COLLECTOR_ID` | `prod-server` | Collector identity for heartbeats |
| `X_COLLECTOR_PROXY_SERVER` | unset | HTTP proxy for browser traffic |
| `X_COLLECTOR_HEADLESS` | `0` | Only set `1` where X has not blocked headless |

## Local checks

```bash
npm install
npm test
npm run build
```
