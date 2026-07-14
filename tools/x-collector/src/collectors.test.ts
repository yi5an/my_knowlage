import { readFile } from "node:fs/promises";

import { describe, expect, it } from "vitest";

import { AccountCollector, extractUserId } from "./account-collector.js";
import { KeywordCollector } from "./keyword-collector.js";
import type { KeywordSearchSession, XWebTransport } from "./session.js";

async function fixture(name: string): Promise<unknown> {
  const url = new URL(`../fixtures/${name}`, import.meta.url);
  return JSON.parse(await readFile(url, "utf8")) as unknown;
}

class FakeTransport implements XWebTransport {
  readonly calls: Array<{operation: string; variables: Record<string, unknown>}> = [];

  constructor(private readonly timeline: unknown) {}

  async query(operation: string, variables: Record<string, unknown>): Promise<unknown> {
    this.calls.push({operation, variables});
    if (operation === "UserByScreenName") {
      return {data: {user: {result: {rest_id: "44196397"}}}};
    }
    return this.timeline;
  }

  async close(): Promise<void> {}
}

class FakeKeywordSession implements KeywordSearchSession {
  readonly calls: Array<{query: string; product: string; count: number}> = [];

  constructor(private readonly timeline: unknown) {}

  async searchLatest(query: string, count: number): Promise<unknown> {
    this.calls.push({query, product: "Latest", count});
    return this.timeline;
  }

  async loginStatus(): Promise<"ready"> {
    return "ready";
  }

  async close(): Promise<void> {}
}

describe("AccountCollector", () => {
  it("reads the user id from the modular Relay response", () => {
    expect(
      extractUserId({
        data: {user_result_by_screen_name: {result: {rest_id: "44196397"}}},
      }),
    ).toBe("44196397");
  });

  it("resolves the user id before requesting the account timeline", async () => {
    const transport = new FakeTransport(await fixture("account-timeline.json"));
    const collector = new AccountCollector(transport);

    const posts = await collector.collect({username: "elonmusk", max_items_per_poll: 1});

    expect(transport.calls).toEqual([
      {operation: "UserByScreenName", variables: {screen_name: "elonmusk"}},
      {
        operation: "UserTweets",
        variables: {
          userId: "44196397",
          screenName: "elonmusk",
          count: 1,
          includePromotedContent: false,
          withVoice: true,
          withV2Timeline: true,
        },
      },
    ]);
    expect(posts).toHaveLength(1);
    expect(posts[0]?.tweet_id).toBe("2075367885438890134");
  });
});

describe("KeywordCollector", () => {
  it("requests latest search results and applies the source limit", async () => {
    const session = new FakeKeywordSession(await fixture("search-timeline.json"));
    const collector = new KeywordCollector(session);

    const posts = await collector.collect({
      query: "Federal Reserve OR 美联储",
      max_items_per_poll: 5,
    });

    expect(session.calls).toEqual([
      {query: "Federal Reserve OR 美联储", product: "Latest", count: 5},
    ]);
    expect(posts).toHaveLength(1);
  });
});
