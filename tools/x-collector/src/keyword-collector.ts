import { normalizeTimeline } from "./normalizer.js";
import type { KeywordSearchSession } from "./session.js";
import type { XPost } from "./types.js";

export interface KeywordSource {
  query: string;
  max_items_per_poll: number;
}

export class KeywordCollector {
  constructor(private readonly session: KeywordSearchSession) {}

  async collect(source: KeywordSource): Promise<XPost[]> {
    const timeline = await this.session.searchLatest(
      source.query,
      source.max_items_per_poll,
    );
    return normalizeTimeline(timeline).slice(0, source.max_items_per_poll);
  }
}
