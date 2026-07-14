import { readFile } from "node:fs/promises";

import { describe, expect, it } from "vitest";

import { normalizeTimeline } from "./normalizer.js";

async function fixture(name: string): Promise<unknown> {
  const url = new URL(`../fixtures/${name}`, import.meta.url);
  return JSON.parse(await readFile(url, "utf8")) as unknown;
}

describe("normalizeTimeline", () => {
  it("normalizes author, metrics, media, and quoted post", async () => {
    const posts = normalizeTimeline(await fixture("account-timeline.json"));

    expect(posts[0]).toMatchObject({
      tweet_id: "2075367885438890134",
      author_id: "44196397",
      author_username: "elonmusk",
      author_name: "Elon Musk",
      text: "Starmind\n\nhttps://t.co/example",
      published_at: "2026-07-09T23:53:57.000Z",
      url: "https://x.com/elonmusk/status/2075367885438890134",
      metrics: {
        like_count: 100,
        repost_count: 20,
        reply_count: 5,
        quote_count: 2,
        bookmark_count: 3,
        view_count: 1000,
      },
    });
    expect(posts[0]?.media).toEqual([
      {
        type: "photo",
        url: "https://pbs.twimg.com/media/example.jpg",
        preview_url: "https://pbs.twimg.com/media/example.jpg",
      },
    ]);
    expect(posts[0]?.quoted_tweet).toMatchObject({
      tweet_id: "2075000000000000000",
      author_username: "x",
      text: "Quoted post",
    });
  });

  it("sorts newest first", async () => {
    const posts = normalizeTimeline(await fixture("account-timeline.json"));
    expect(posts.map((post) => post.tweet_id)).toEqual([
      "2075367885438890134",
      "1519480761749016577",
    ]);
  });

  it("deduplicates repeated timeline entries by tweet id", async () => {
    const posts = normalizeTimeline(await fixture("search-timeline.json"));
    expect(posts).toHaveLength(1);
  });

  it("normalizes the modular Relay tweet shape", async () => {
    const posts = normalizeTimeline(await fixture("relay-account-timeline.json"));

    expect(posts).toHaveLength(1);
    expect(posts[0]).toMatchObject({
      tweet_id: "1519480761749016577",
      author_id: "44196397",
      author_username: "elonmusk",
      author_name: "Elon Musk",
      text: "Next I’m buying Coca-Cola",
      published_at: "2022-04-28T00:56:58.000Z",
      metrics: {
        like_count: 100,
        repost_count: 20,
        reply_count: 5,
        quote_count: 2,
        bookmark_count: 3,
        view_count: 1000,
      },
    });
  });
});
