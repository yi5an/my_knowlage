import { normalizeTimeline } from "./normalizer.js";
import type { XWebTransport } from "./session.js";
import type { JsonObject, XPost } from "./types.js";

export interface AccountSource {
  username: string;
  max_items_per_poll: number;
}

export class AccountCollector {
  constructor(private readonly transport: XWebTransport) {}

  async collect(source: AccountSource): Promise<XPost[]> {
    const userPayload = await this.transport.query("UserByScreenName", {
      screen_name: source.username,
    });
    const userId = extractUserId(userPayload);
    const timeline = await this.transport.query("UserTweets", {
      userId,
      screenName: source.username,
      count: source.max_items_per_poll,
      includePromotedContent: false,
      withVoice: true,
      withV2Timeline: true,
    });
    return normalizeTimeline(timeline).slice(0, source.max_items_per_poll);
  }
}

export function extractUserId(payload: unknown): string {
  const data = asObject(payload)?.data;
  const dataObject = asObject(data);
  const user =
    asObject(asObject(dataObject?.user_result_by_screen_name)?.result) ??
    asObject(asObject(dataObject?.user)?.result);
  const result = asObject(user);
  const visibleUser = result?.__typename === "UserUnavailable" ? undefined : result;
  const userId = visibleUser?.rest_id;
  if (typeof userId !== "string" || !userId) {
    throw new Error("X user id not found");
  }
  return userId;
}

function asObject(value: unknown): JsonObject | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as JsonObject)
    : undefined;
}
