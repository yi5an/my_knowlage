import { AccountCollector } from "./account-collector.js";
import type { AccountSource } from "./account-collector.js";
import type { XCollectorCommandComplete, XCollectorCommandResponse } from "./backend-types.js";
import { BackendClient } from "./backend-client.js";
import type { CollectorConfig } from "./config.js";
import { KeywordCollector } from "./keyword-collector.js";
import { FileSpool } from "./spool.js";
import { createGuestTransport, PlaywrightKeywordSearchSession } from "./session.js";
import type { XPost } from "./types.js";

interface RuntimeClient {
  claimCommands(collectorId: string): Promise<XCollectorCommandResponse[]>;
  heartbeat(payload: {
    collector_id: string;
    version: string;
    login_status: "uninitialized" | "ready" | "auth_required" | "challenge_required";
    queue_size: number;
    last_error?: string;
  }): Promise<unknown>;
  importPosts(sourceId: string, collectorId: string, posts: XPost[]): Promise<unknown>;
  completeCommand(jobId: string, payload: XCollectorCommandComplete): Promise<unknown>;
}

interface RuntimeSpool {
  take(): Promise<{created_at: string; source_id: string; posts: XPost[]} | null>;
  enqueue(batch: {created_at: string; source_id: string; posts: XPost[]}): Promise<void>;
}

interface RuntimeSession {
  posts: XPost[];
  close(): Promise<void>;
}

export interface RuntimeDependencies {
  client: RuntimeClient;
  spool: RuntimeSpool;
  collectAccount(source: AccountSource): Promise<RuntimeSession>;
  collectKeyword(source: {query: string; max_items_per_poll: number}): Promise<RuntimeSession>;
}

export async function runOnce(
  config: CollectorConfig,
  dependencies: RuntimeDependencies = defaultDependencies(config),
): Promise<void> {
  await dependencies.client.heartbeat({
    collector_id: config.collectorId,
    version: config.version,
    login_status: "ready",
    queue_size: 0,
  });
  await drainSpool(config, dependencies);
  const commands = await dependencies.client.claimCommands(config.collectorId);
  for (const command of commands) {
    await runCommand(config, dependencies, command);
  }
}

export async function runLoop(
  config: CollectorConfig,
  once = false,
  dependencies?: RuntimeDependencies,
): Promise<void> {
  const resolved = dependencies ?? defaultDependencies(config);
  do {
    try {
      await runOnce(config, resolved);
    } catch (error) {
      await resolved.client.heartbeat({
        collector_id: config.collectorId,
        version: config.version,
        login_status: "uninitialized",
        queue_size: 0,
        last_error: error instanceof Error ? error.message.slice(0, 1000) : String(error),
      }).catch(() => undefined);
      if (once) throw error;
    }
    if (!once) await new Promise((resolve) => setTimeout(resolve, config.pollIntervalMs));
  } while (!once);
}

async function drainSpool(config: CollectorConfig, dependencies: RuntimeDependencies): Promise<void> {
  while (true) {
    const batch = await dependencies.spool.take();
    if (!batch) return;
    try {
      await dependencies.client.importPosts(batch.source_id, config.collectorId, batch.posts);
    } catch (error) {
      await dependencies.spool.enqueue(batch);
      throw error;
    }
  }
}

async function runCommand(
  config: CollectorConfig,
  dependencies: RuntimeDependencies,
  command: XCollectorCommandResponse,
): Promise<void> {
  let session: RuntimeSession | null = null;
  try {
    if (command.mode === "account") {
      session = await dependencies.collectAccount({
        username: String(command.config.username),
        max_items_per_poll: Number(command.config.max_items_per_poll ?? 50),
      });
    } else {
      session = await dependencies.collectKeyword({
        query: String(command.config.query),
        max_items_per_poll: Number(command.config.max_items_per_poll ?? 50),
      });
    }
    const result = await dependencies.client.importPosts(
      command.source_id,
      config.collectorId,
      session.posts,
    ) as {items_created?: number; items_updated?: number; items_skipped?: number};
    await dependencies.client.completeCommand(command.job_id, {
      status: "succeeded",
      items_seen: session.posts.length,
      items_created: Number(result.items_created ?? 0),
      items_updated: Number(result.items_updated ?? 0),
      items_skipped: Number(result.items_skipped ?? 0),
    });
  } catch (error) {
    await dependencies.client.completeCommand(command.job_id, {
      status: "failed",
      items_seen: 0,
      items_created: 0,
      items_updated: 0,
      items_skipped: 0,
      error: error instanceof Error ? error.message.slice(0, 1000) : String(error),
    }).catch(() => undefined);
  } finally {
    await session?.close();
  }
}

function defaultDependencies(config: CollectorConfig): RuntimeDependencies {
  const client = new BackendClient(config.backendUrl, config.token);
  const spool = new FileSpool(config.spoolDir, {maxBytes: config.maxSpoolBytes});
  return {
    client,
    spool,
    collectAccount: async (source) => {
      const transport = await createGuestTransport();
      try {
        const posts = await new AccountCollector(transport).collect(source);
        return {posts, close: () => transport.close()};
      } catch (error) {
        await transport.close();
        throw error;
      }
    },
    collectKeyword: async (source) => {
      const session = await PlaywrightKeywordSearchSession.open(config.profileDir);
      try {
        const posts = await new KeywordCollector(session).collect(source);
        return {posts, close: () => session.close()};
      } catch (error) {
        await session.close();
        throw error;
      }
    },
  };
}
