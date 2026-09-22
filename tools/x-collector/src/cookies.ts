// Netscape cookie-file injection for the collector's persistent profile.
import {readFileSync} from "node:fs";

import {chromium} from "playwright";

export interface ParsedCookie {
  name: string;
  value: string;
  domain: string;
  path: string;
  expires: number;
  secure: boolean;
}

export function parseNetscapeCookies(text: string): ParsedCookie[] {
  const cookies: ParsedCookie[] = [];
  for (const line of text.split("\n")) {
    if (!line.trim() || line.startsWith("#")) continue;
    const parts = line.trim().split(/\s+/);
    if (parts.length < 7) continue;
    const [domain = "", , path = "/", secure = "", expiry = "", name = "", ...rest] = parts;
    const value = rest.join(" ");
    const expires = Number(expiry) > 0 ? Number(expiry) : -1;
    cookies.push({
      name,
      value,
      domain,
      path: path || "/",
      expires,
      secure: secure.toUpperCase() === "TRUE",
    });
  }
  return cookies;
}

export async function injectCookies(
  profileDir: string,
  cookieFile: string,
  options: {headless?: boolean; proxyServer?: string} = {},
): Promise<{logged_in: boolean; url: string; cookies: number}> {
  const cookies = parseNetscapeCookies(readFileSync(cookieFile, "utf8"));
  if (!cookies.some((cookie) => cookie.name === "auth_token")) {
    throw new Error("cookie file has no auth_token; export x.com cookies again");
  }
  const context = await chromium.launchPersistentContext(profileDir, {
    headless: options.headless ?? false,
    locale: "en-US",
    proxy: options.proxyServer ? {server: options.proxyServer} : undefined,
  });
  try {
    await context.addCookies(cookies);
    const pages = context.pages();
    const page = pages[0] ?? (await context.newPage());
    await page
      .goto("https://x.com/home", {waitUntil: "domcontentloaded", timeout: 45_000})
      .catch(() => {});
    await page.waitForTimeout(5000);
    const switcher = await page
      .locator('[data-testid="SideNav_AccountSwitcher_Button"]')
      .count()
      .catch(() => 0);
    return {logged_in: switcher > 0, url: page.url(), cookies: cookies.length};
  } finally {
    await context.close();
  }
}
