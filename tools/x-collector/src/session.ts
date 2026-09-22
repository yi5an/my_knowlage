import { discoverOperationsFromBundles } from "./query-discovery.js";
import type { DiscoveredOperation } from "./query-discovery.js";
import { chromium } from "playwright";
import type { BrowserContext, Page } from "playwright";

export interface XWebTransport {
  query(operation: string, variables: Record<string, unknown>): Promise<unknown>;
  close(): Promise<void>;
}

export type LoginStatus = "uninitialized" | "ready" | "auth_required" | "challenge_required";

export interface KeywordSearchSession {
  searchLatest(query: string, count: number): Promise<unknown>;
  loginStatus(): Promise<LoginStatus>;
  close(): Promise<void>;
}

export class CollectorSessionError extends Error {
  constructor(
    readonly code: "network_error" | "rate_limited" | "auth_required" | "challenge_required" | "query_changed",
    message: string,
    readonly retryAfterMs?: number,
  ) {
    super(message);
    this.name = "CollectorSessionError";
  }
}

export class OperationRegistry {
  private sources: string[] | null = null;
  private readonly operations = new Map<string, DiscoveredOperation>();

  constructor(private readonly loadBundles: () => Promise<string[]>) {}

  async get(name: string): Promise<DiscoveredOperation> {
    const cached = this.operations.get(name);
    if (cached) return cached;
    this.sources ??= await this.loadBundles();
    const discovered = discoverOperationsFromBundles(this.sources, [name])[name];
    if (!discovered) throw new CollectorSessionError("query_changed", `Missing ${name}`);
    this.operations.set(name, discovered);
    return discovered;
  }

  invalidate(): void {
    this.sources = null;
    this.operations.clear();
  }
}

export interface GraphqlRequest {
  url: string;
}

export interface GuestCredentials {
  authorization: string;
  guestToken: string;
}

export interface JsonResponse {
  status: number;
  headers: Record<string, string>;
  body: unknown;
}

export type RequestJson = (
  request: GraphqlRequest,
  headers: Record<string, string>,
) => Promise<JsonResponse>;

export class GuestXWebTransport implements XWebTransport {
  constructor(
    private readonly registry: OperationRegistry,
    private readonly credentials: GuestCredentials,
    private readonly requestJson: RequestJson,
    private readonly closeSession: () => Promise<void>,
  ) {}

  async query(operationName: string, variables: Record<string, unknown>): Promise<unknown> {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const operation = await this.registry.get(operationName);
      const normalizedVariables = normalizeOperationVariables(
        operationName,
        operation.protocol,
        variables,
      );
      const response = await this.requestJson(
        buildGraphqlRequest(operationName, operation, normalizedVariables),
        {
          authorization: this.credentials.authorization,
          "x-guest-token": this.credentials.guestToken,
          "x-twitter-active-user": "yes",
          "x-twitter-client-language": "en",
        },
      );
      const error = classifyResponseStatus(response.status, response.headers);
      if (!error) return response.body;
      if (error.code === "query_changed" && attempt === 0) {
        this.registry.invalidate();
        continue;
      }
      throw error;
    }
    throw new CollectorSessionError("query_changed", `Unable to refresh ${operationName}`);
  }

  async close(): Promise<void> {
    await this.closeSession();
  }
}

export function buildGraphqlRequest(
  operationName: string,
  operation: DiscoveredOperation,
  variables: Record<string, unknown>,
): GraphqlRequest {
  const url = new URL(
    `https://api.x.com/graphql/${encodeURIComponent(operation.queryId)}/${encodeURIComponent(operationName)}`,
  );
  url.searchParams.set("variables", JSON.stringify(variables));
  url.searchParams.set(
    "features",
    JSON.stringify(Object.fromEntries(operation.featureSwitches.map((name) => [name, true]))),
  );
  url.searchParams.set(
    "fieldToggles",
    JSON.stringify(Object.fromEntries(operation.fieldToggles.map((name) => [name, false]))),
  );
  return {url: url.toString()};
}

export function normalizeOperationVariables(
  operationName: string,
  protocol: DiscoveredOperation["protocol"],
  variables: Record<string, unknown>,
): Record<string, unknown> {
  if (protocol === "relay") {
    const providedVariables = {
      __relay_internal__pv__appviewerisloggedinprovider: false,
    };
    if (operationName === "UserByScreenName") {
      return {
        screenName: variables.screenName ?? variables.screen_name,
        ...providedVariables,
      };
    }
    if (operationName === "UserTweets") {
      return {
        screenName: variables.screenName,
        count: variables.count,
        cursor: variables.cursor ?? null,
        ...providedVariables,
      };
    }
    return variables;
  }

  const normalized = {...variables};
  delete normalized.screenName;
  return normalized;
}

export function classifyResponseStatus(
  status: number,
  headers: Record<string, string>,
): CollectorSessionError | null {
  if (status >= 200 && status < 300) return null;
  if (status === 401 || status === 403) {
    return new CollectorSessionError("auth_required", `X Web authentication failed (${status})`);
  }
  if (status === 429) {
    const retryAfterSeconds = Number(headers["retry-after"] ?? "");
    const retryAfterMs = Number.isFinite(retryAfterSeconds)
      ? Math.max(0, retryAfterSeconds * 1000)
      : undefined;
    return new CollectorSessionError("rate_limited", "X Web rate limited", retryAfterMs);
  }
  if (status === 400 || status === 404) {
    return new CollectorSessionError("query_changed", `X Web query failed (${status})`);
  }
  return new CollectorSessionError("network_error", `X Web request failed (${status})`);
}

export function selectMainJsUrl(urls: string[]): string {
  const url = urls.find((candidate) => /\/main\.[A-Za-z0-9_-]+\.js(?:\?|$)/.test(candidate));
  if (!url) throw new CollectorSessionError("query_changed", "X Web main.js was not found");
  return url;
}

export async function waitForMainJsUrl(
  readUrls: () => Promise<string[]>,
  waitForScripts: () => Promise<void>,
  observedUrls: string[] = [],
): Promise<string> {
  const initial = [...observedUrls, ...(await readUrls())];
  try {
    return selectMainJsUrl(initial);
  } catch (error) {
    if (!(error instanceof CollectorSessionError) || error.code !== "query_changed") throw error;
    await waitForScripts();
    return selectMainJsUrl([...observedUrls, ...(await readUrls())]);
  }
}

export function isSearchTimelineUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.host === "api.x.com" && url.pathname.includes("/SearchTimeline");
  } catch {
    return false;
  }
}

export function detectLoginStatus(
  url: string,
  hasAccountSwitcher: boolean,
  hasChallenge: boolean,
): LoginStatus {
  if (hasChallenge || url.includes("/account/access")) return "challenge_required";
  if (url.includes("/i/flow/login")) return "auth_required";
  if (hasAccountSwitcher) return "ready";
  return "uninitialized";
}

export interface GuestTransportOptions {
  headless?: boolean;
  profileUrl?: string;
  timeoutMs?: number;
}

export async function createGuestTransport(
  options: GuestTransportOptions = {},
): Promise<GuestXWebTransport> {
  const timeoutMs = options.timeoutMs ?? 45_000;
  const browser = await chromium.launch({headless: options.headless ?? true});
  const context = await browser.newContext({locale: "en-US"});
  const page = await context.newPage();
  let observedBundleJobs: Array<Promise<string | null>> = [];
  page.on("response", (response) => {
    if (response.request().resourceType() !== "script") return;
    observedBundleJobs.push(response.text().catch(() => null));
  });
  try {
    const credentialsPromise = waitForGuestCredentials(page, timeoutMs);
    await page.goto(options.profileUrl ?? "https://x.com/elonmusk", {
      waitUntil: "commit",
      timeout: timeoutMs,
    });
    const credentials = await credentialsPromise;
    let loadedOnce = false;
    const registry = new OperationRegistry(async () => {
      if (loadedOnce) {
        observedBundleJobs = [];
        await page.reload({waitUntil: "domcontentloaded", timeout: timeoutMs});
      } else {
        await page.waitForLoadState("domcontentloaded", {timeout: timeoutMs});
      }
      loadedOnce = true;
      await page.locator("article").first().waitFor({state: "attached", timeout: timeoutMs});
      const settled = await Promise.allSettled([...observedBundleJobs]);
      return settled
        .filter((result): result is PromiseFulfilledResult<string | null> => result.status === "fulfilled")
        .map((result) => result.value)
        .filter((source): source is string => Boolean(source));
    });
    return new GuestXWebTransport(
      registry,
      credentials,
      async (request, headers) => {
        const response = await context.request.get(request.url, {headers, timeout: timeoutMs});
        return {
          status: response.status(),
          headers: response.headers(),
          body: await response.json().catch(() => null),
        };
      },
      async () => browser.close(),
    );
  } catch (error) {
    await browser.close();
    throw toSessionError(error);
  }
}

export class PlaywrightKeywordSearchSession implements KeywordSearchSession {
  private constructor(
    private readonly context: BrowserContext,
    private readonly page: Page,
    private readonly timeoutMs: number,
  ) {}

  static async open(
    profileDir: string,
    options: {headless?: boolean; timeoutMs?: number} = {},
  ): Promise<PlaywrightKeywordSearchSession> {
    const context = await chromium.launchPersistentContext(profileDir, {
      headless: options.headless ?? true,
      locale: "en-US",
    });
    const pages = context.pages();
    const page = pages[0] ?? (await context.newPage());
    return new PlaywrightKeywordSearchSession(context, page, options.timeoutMs ?? 45_000);
  }

  async loginStatus(): Promise<LoginStatus> {
    if (this.page.url() === "about:blank") {
      await this.page.goto("https://x.com/home", {
        waitUntil: "domcontentloaded",
        timeout: this.timeoutMs,
      });
    }
    const hasAccountSwitcher =
      (await this.page.locator('[data-testid="SideNav_AccountSwitcher_Button"]').count()) > 0;
    return detectLoginStatus(
      this.page.url(),
      hasAccountSwitcher,
      this.page.url().includes("/account/access"),
    );
  }

  async searchLatest(query: string, count: number): Promise<unknown> {
    const status = await this.loginStatus();
    if (status !== "ready") {
      const errorCode = status === "uninitialized" ? "auth_required" : status;
      throw new CollectorSessionError(errorCode, `X login is not ready (${status})`);
    }

    const responsePromise = this.page.waitForResponse(
      (response) => isSearchTimelineUrl(response.url()),
      {timeout: this.timeoutMs},
    );
    const url = new URL("https://x.com/search");
    url.searchParams.set("q", query);
    url.searchParams.set("src", "typed_query");
    url.searchParams.set("f", "live");
    await this.page.goto(url.toString(), {waitUntil: "commit", timeout: this.timeoutMs});

    try {
      const response = await responsePromise;
      const error = classifyResponseStatus(response.status(), response.headers());
      if (error) throw error;
      const payload = await response.json();
      const posts = Array.isArray(payload) ? payload.slice(0, count) : payload;
      return posts;
    } catch (error) {
      const currentStatus = await this.loginStatus().catch(() => "uninitialized" as const);
      if (currentStatus === "auth_required" || currentStatus === "challenge_required") {
        throw new CollectorSessionError(currentStatus, `X login is not ready (${currentStatus})`);
      }
      throw toSessionError(error);
    }
  }

  async close(): Promise<void> {
    await this.context.close();
  }
}

export async function waitForGuestCredentials(
  page: Page,
  timeoutMs: number,
): Promise<GuestCredentials> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new CollectorSessionError("network_error", "X guest activation timed out")),
      timeoutMs,
    );
    page.on("response", async (response) => {
      try {
        const request = response.request();
        const headers = await request.allHeaders();
        const pathname = new URL(response.url()).pathname;
        if (pathname !== "/1.1/guest/activate.json") {
          // Since ~2026-09 the anonymous web app no longer calls
          // guest/activate.json. Guest-authenticated API requests carry the
          // token in the x-guest-token request header instead, so steal the
          // credentials from any such request (e.g. viewer.json).
          const headerToken = headers["x-guest-token"];
          if (!headerToken || !headers.authorization) return;
          clearTimeout(timer);
          resolve({authorization: headers.authorization, guestToken: headerToken});
          return;
        }
        const error = classifyResponseStatus(response.status(), response.headers());
        if (error) throw error;
        const body = (await response.json()) as {guest_token?: unknown};
        const authorization = headers.authorization;
        const guestToken = typeof body.guest_token === "string" ? body.guest_token : null;
        if (!authorization || !guestToken) {
          throw new CollectorSessionError("auth_required", "X guest credentials were missing");
        }
        clearTimeout(timer);
        resolve({authorization, guestToken});
      } catch (error) {
        clearTimeout(timer);
        reject(toSessionError(error));
      }
    });
  });
}

function toSessionError(error: unknown): CollectorSessionError {
  if (error instanceof CollectorSessionError) return error;
  const message = error instanceof Error ? error.message : String(error);
  return new CollectorSessionError("network_error", message.slice(0, 500));
}
