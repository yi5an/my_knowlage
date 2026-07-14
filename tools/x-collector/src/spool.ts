import { mkdir, readFile, readdir, rename, rm, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";

import type { XPost } from "./types.js";

export interface SpoolBatch {
  created_at: string;
  source_id: string;
  posts: XPost[];
}

export class SpoolQuotaError extends Error {
  constructor() {
    super("X collector spool quota exceeded");
    this.name = "SpoolQuotaError";
  }
}

export class FileSpool {
  constructor(
    private readonly directory: string,
    private readonly options: {maxBytes: number},
  ) {}

  async enqueue(batch: SpoolBatch): Promise<void> {
    await mkdir(this.directory, {recursive: true});
    const serialized = JSON.stringify(batch);
    const currentBytes = await this.bytesOnDisk();
    if (currentBytes + Buffer.byteLength(serialized) > this.options.maxBytes) {
      throw new SpoolQuotaError();
    }
    const safeTimestamp = batch.created_at.replace(/[^0-9A-Za-z_-]/g, "-");
    const filename = `${safeTimestamp}-${crypto.randomUUID()}.json`;
    const temporary = join(this.directory, `.${filename}.tmp`);
    const target = join(this.directory, filename);
    await writeFile(temporary, serialized, {encoding: "utf8", mode: 0o600});
    await rename(temporary, target);
  }

  async peek(): Promise<SpoolBatch | null> {
    const filename = await this.oldestFilename();
    if (!filename) return null;
    return JSON.parse(await readFile(join(this.directory, filename), "utf8")) as SpoolBatch;
  }

  async take(): Promise<SpoolBatch | null> {
    const filename = await this.oldestFilename();
    if (!filename) return null;
    const target = join(this.directory, filename);
    const batch = JSON.parse(await readFile(target, "utf8")) as SpoolBatch;
    await rm(target);
    return batch;
  }

  private async oldestFilename(): Promise<string | null> {
    await mkdir(this.directory, {recursive: true});
    const filenames = (await readdir(this.directory))
      .filter((filename) => filename.endsWith(".json"))
      .sort();
    return filenames[0] ?? null;
  }

  private async bytesOnDisk(): Promise<number> {
    const filenames = (await readdir(this.directory).catch(() => []))
      .filter((filename) => filename.endsWith(".json"));
    const sizes = await Promise.all(
      filenames.map(async (filename) => (await stat(join(this.directory, filename))).size),
    );
    return sizes.reduce((total, size) => total + size, 0);
  }
}
