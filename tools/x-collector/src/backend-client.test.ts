import { describe, expect, it, vi } from "vitest";

import { BackendClient } from "./backend-client.js";

describe("BackendClient", () => {
  it("posts normalized items to the X import endpoint", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({items_created: 2}), {status: 200}));
    const client = new BackendClient("http://127.0.0.1:8010", "collector-token", fetchImpl);

    const result = await client.importPosts("source-1", "collector-1", [
      {
        tweet_id: "1",
        author_id: "2",
        author_username: "elonmusk",
        author_name: "Elon Musk",
        text: "hello",
        published_at: "2026-07-14T00:00:00.000Z",
        url: "https://x.com/elonmusk/status/1",
        conversation_id: "1",
        lang: "en",
        media: [],
        quoted_tweet: null,
        reposted_tweet: null,
        reply_to_tweet_id: null,
        metrics: {like_count: 1, repost_count: null, reply_count: null, quote_count: null, bookmark_count: null, view_count: null},
        raw_payload: {},
      },
    ]);

    expect(result).toEqual({items_created: 2});
    const calls = fetchImpl.mock.calls as unknown as Array<[string, RequestInit]>;
    expect(calls[0]?.[0]).toBe(
      "http://127.0.0.1:8010/api/v1/investment/import/x-posts",
    );
    const request = calls[0]?.[1];
    expect(request).toBeDefined();
    if (!request) throw new Error("fetch request was not captured");
    expect(request.method).toBe("POST");
    expect((request.headers as Headers).get("content-type")).toBe("application/json");
    expect((request.headers as Headers).get("authorization")).toBe("Bearer collector-token");
    const body = JSON.parse(request.body as string) as {source_id: string; items: unknown[]};
    expect(body.source_id).toBe("source-1");
    expect(body.items).toHaveLength(1);
  });
});
