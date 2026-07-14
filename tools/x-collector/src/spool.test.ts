import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { FileSpool, SpoolQuotaError } from "./spool.js";

const directories: string[] = [];

async function tempDirectory(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), "knowpilot-x-spool-"));
  directories.push(directory);
  return directory;
}

afterEach(async () => {
  await Promise.all(directories.splice(0).map((directory) => rm(directory, {recursive: true, force: true})));
});

describe("FileSpool", () => {
  it("replays queued batches oldest first after restart", async () => {
    const directory = await tempDirectory();
    const first = new FileSpool(directory, {maxBytes: 1_000_000});
    await first.enqueue({created_at: "2026-07-14T01:00:00.000Z", source_id: "a", posts: []});
    await first.enqueue({created_at: "2026-07-14T02:00:00.000Z", source_id: "b", posts: []});

    const reopened = new FileSpool(directory, {maxBytes: 1_000_000});
    expect((await reopened.peek())?.created_at).toBe("2026-07-14T01:00:00.000Z");
    expect((await reopened.take())?.source_id).toBe("a");
    expect((await reopened.take())?.source_id).toBe("b");
    expect(await reopened.take()).toBeNull();
  });

  it("refuses writes that exceed the configured quota", async () => {
    const spool = new FileSpool(await tempDirectory(), {maxBytes: 20});
    await expect(
      spool.enqueue({created_at: "2026-07-14T01:00:00.000Z", source_id: "a", posts: []}),
    ).rejects.toBeInstanceOf(SpoolQuotaError);
  });
});
