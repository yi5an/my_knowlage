import { describe, expect, it } from "vitest";

import { runOnce } from "./runtime.js";
import type { CollectorConfig } from "./config.js";
import type { XCollectorCommandResponse } from "./backend-types.js";
import type { XPost } from "./types.js";

const config: CollectorConfig = {
  backendUrl: "http://127.0.0.1:8010",
  collectorId: "collector-test",
  version: "0.1.0",
  dataDir: "/tmp/x-collector",
  profileDir: "/tmp/x-collector/profile",
  spoolDir: "/tmp/x-collector/spool",
  maxSpoolBytes: 1_000_000,
  pollIntervalMs: 60_000,
  headless: false,
};

const post: XPost = {
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
};

const command: XCollectorCommandResponse = {
  job_id: "job-1",
  source_id: "source-1",
  workspace_id: "ws_default",
  name: "Elon",
  mode: "account",
  config: {mode: "account", username: "elonmusk", max_items_per_poll: 5},
  poll_interval_seconds: 900,
};

describe("runOnce", () => {
  it("collects a claimed command, uploads posts, and completes the job", async () => {
    const calls: string[] = [];
    const dependencies = {
      client: {
        claimCommands: async () => [command],
        heartbeat: async () => { calls.push("heartbeat"); },
        importPosts: async () => { calls.push("import"); return {}; },
        completeCommand: async () => { calls.push("complete"); },
      },
      spool: {
        take: async () => null,
        enqueue: async () => { calls.push("spool"); },
      },
      collectAccount: async () => ({posts: [post], close: async () => { calls.push("close"); }}),
      collectKeyword: async () => ({posts: [], close: async () => {}}),
    };

    await runOnce(config, dependencies);

    expect(calls).toEqual(["heartbeat", "import", "complete", "close"]);
  });
});
