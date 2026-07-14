import { describe, expect, it, vi } from "vitest";

import {
  CollectorSessionError,
  GuestXWebTransport,
  OperationRegistry,
  buildGraphqlRequest,
  classifyResponseStatus,
  detectLoginStatus,
  isSearchTimelineUrl,
  normalizeOperationVariables,
  selectMainJsUrl,
  waitForMainJsUrl,
} from "./session.js";

const MAIN_JS = `queryId:"account-query",operationName:"UserTweets",operationType:"query",
metadata:{featureSwitches:["feature_one"],fieldToggles:["withArticlePlainText"]}}`;

describe("OperationRegistry", () => {
  it("caches the current main.js and reloads after invalidation", async () => {
    const loader = vi.fn(async () => [MAIN_JS]);
    const registry = new OperationRegistry(loader);

    expect((await registry.get("UserTweets")).queryId).toBe("account-query");
    expect((await registry.get("UserTweets")).queryId).toBe("account-query");
    expect(loader).toHaveBeenCalledTimes(1);

    registry.invalidate();
    expect((await registry.get("UserTweets")).queryId).toBe("account-query");
    expect(loader).toHaveBeenCalledTimes(2);
  });
});

describe("buildGraphqlRequest", () => {
  it("uses discovered switches without embedding credentials in the URL", () => {
    const request = buildGraphqlRequest(
      "UserTweets",
      {
        queryId: "account-query",
        protocol: "legacy",
        featureSwitches: ["feature_one"],
        fieldToggles: ["withArticlePlainText"],
      },
      {userId: "44196397", count: 5},
    );

    const url = new URL(request.url);
    expect(url.pathname).toBe("/graphql/account-query/UserTweets");
    expect(JSON.parse(url.searchParams.get("features") ?? "{}")).toEqual({
      feature_one: true,
    });
    expect(JSON.parse(url.searchParams.get("fieldToggles") ?? "{}")).toEqual({
      withArticlePlainText: false,
    });
    expect(request.url).not.toContain("Bearer");
  });

  it("converts account variables for Relay profile queries", () => {
    expect(
      normalizeOperationVariables(
        "UserTweets",
        "relay",
        {screenName: "elonmusk", userId: "44196397", count: 5, withVoice: true},
      ),
    ).toEqual({
      screenName: "elonmusk",
      count: 5,
      cursor: null,
      __relay_internal__pv__appviewerisloggedinprovider: false,
    });
    expect(
      normalizeOperationVariables(
        "UserByScreenName",
        "relay",
        {screen_name: "elonmusk"},
      ),
    ).toEqual({
      screenName: "elonmusk",
      __relay_internal__pv__appviewerisloggedinprovider: false,
    });
  });
});

describe("classifyResponseStatus", () => {
  it.each([
    [401, "auth_required"],
    [403, "auth_required"],
    [429, "rate_limited"],
  ] as const)("maps HTTP %s to %s", (status, code) => {
    const error = classifyResponseStatus(status, {"retry-after": "2"});
    expect(error).toBeInstanceOf(CollectorSessionError);
    expect(error?.code).toBe(code);
    if (status === 429) expect(error?.retryAfterMs).toBe(2000);
  });

  it("returns no error for success", () => {
    expect(classifyResponseStatus(200, {})).toBeNull();
  });
});

describe("GuestXWebTransport", () => {
  it("injects ephemeral Web credentials and returns the response body", async () => {
    const registry = new OperationRegistry(async () => [MAIN_JS]);
    const requestJson = vi.fn(async () => ({
      status: 200,
      headers: {},
      body: {data: {ok: true}},
    }));
    const transport = new GuestXWebTransport(
      registry,
      {authorization: "Bearer redacted", guestToken: "guest-redacted"},
      requestJson,
      async () => {},
    );

    await expect(transport.query("UserTweets", {count: 5})).resolves.toEqual({
      data: {ok: true},
    });
    expect(requestJson).toHaveBeenCalledWith(
      expect.objectContaining({url: expect.stringContaining("/UserTweets")}),
      {
        authorization: "Bearer redacted",
        "x-guest-token": "guest-redacted",
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
      },
    );
  });

  it("rediscovers and retries once after a changed query", async () => {
    const loader = vi.fn(async () => [MAIN_JS]);
    const registry = new OperationRegistry(loader);
    const requestJson = vi
      .fn()
      .mockResolvedValueOnce({status: 404, headers: {}, body: {}})
      .mockResolvedValueOnce({status: 200, headers: {}, body: {data: {ok: true}}});
    const transport = new GuestXWebTransport(
      registry,
      {authorization: "Bearer redacted", guestToken: "guest-redacted"},
      requestJson,
      async () => {},
    );

    await expect(transport.query("UserTweets", {count: 5})).resolves.toEqual({
      data: {ok: true},
    });
    expect(loader).toHaveBeenCalledTimes(2);
    expect(requestJson).toHaveBeenCalledTimes(2);
  });
});

describe("Playwright session helpers", () => {
  it("selects the current X main bundle", () => {
    expect(
      selectMainJsUrl([
        "https://abs.twimg.com/responsive-web/client-web/vendor.abc.js",
        "https://abs.twimg.com/responsive-web/client-web/main.123.js",
      ]),
    ).toBe("https://abs.twimg.com/responsive-web/client-web/main.123.js");
  });

  it("waits for the main bundle when credentials arrive before scripts", async () => {
    const readUrls = vi
      .fn()
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        "https://abs.twimg.com/responsive-web/client-web/main.123.js",
      ]);
    const waitForScripts = vi.fn(async () => {});

    await expect(waitForMainJsUrl(readUrls, waitForScripts)).resolves.toContain(
      "main.123.js",
    );
    expect(waitForScripts).toHaveBeenCalledOnce();
  });

  it("uses an observed script response when guest SSR has no script tags", async () => {
    const readUrls = vi.fn(async () => []);
    const waitForScripts = vi.fn(async () => {});

    await expect(
      waitForMainJsUrl(readUrls, waitForScripts, [
        "https://abs.twimg.com/responsive-web/client-web/main.network.js",
      ]),
    ).resolves.toContain("main.network.js");
    expect(waitForScripts).not.toHaveBeenCalled();
  });

  it("recognizes only SearchTimeline GraphQL responses", () => {
    expect(
      isSearchTimelineUrl("https://api.x.com/graphql/id/SearchTimeline?variables=x"),
    ).toBe(true);
    expect(isSearchTimelineUrl("https://api.x.com/graphql/id/UserTweets")).toBe(false);
  });

  it.each([
    ["https://x.com/i/flow/login", false, false, "auth_required"],
    ["https://x.com/account/access", false, true, "challenge_required"],
    ["https://x.com/home", true, false, "ready"],
    ["https://x.com/home", false, false, "uninitialized"],
  ] as const)("maps page state to %s", (url, hasAccountSwitcher, hasChallenge, expected) => {
    expect(detectLoginStatus(url, hasAccountSwitcher, hasChallenge)).toBe(expected);
  });
});
