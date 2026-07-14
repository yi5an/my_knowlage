import type { JsonObject, XMedia, XPost, XPostReference } from "./types.js";

const MAX_DEPTH = 40;
const MAX_VISITED_NODES = 20_000;

export function normalizeTimeline(payload: unknown): XPost[] {
  const posts = new Map<string, XPost>();
  let visited = 0;

  const walk = (value: unknown, depth: number): void => {
    if (depth > MAX_DEPTH || visited >= MAX_VISITED_NODES || !isObject(value)) return;
    visited += 1;

    const tweetResults = asObject(value.tweet_results);
    const result = unwrapTweetResult(tweetResults?.result);
    if (result) {
      const post = normalizeTweetResult(result);
      if (post) posts.set(post.tweet_id, post);
    }

    for (const child of Object.values(value)) {
      if (Array.isArray(child)) {
        for (const item of child) walk(item, depth + 1);
      } else if (isObject(child)) {
        walk(child, depth + 1);
      }
    }
  };

  walk(payload, 0);
  return [...posts.values()].sort(
    (left, right) => Date.parse(right.published_at) - Date.parse(left.published_at),
  );
}

function normalizeTweetResult(result: JsonObject): XPost | null {
  const legacy = asObject(result.legacy);
  const user = asObject(asObject(asObject(result.core)?.user_results)?.result);
  const userLegacy = asObject(user?.legacy);
  const tweetId = stringValue(result.rest_id);
  const username = stringValue(userLegacy?.screen_name);
  const createdAt = stringValue(legacy?.created_at);
  if (!tweetId || !username || !createdAt) return null;

  const publishedAt = new Date(createdAt);
  if (Number.isNaN(publishedAt.getTime())) return null;

  return {
    tweet_id: tweetId,
    author_id: stringValue(user?.rest_id),
    author_username: username,
    author_name: stringValue(userLegacy?.name),
    text: stringValue(legacy?.full_text) ?? "",
    published_at: publishedAt.toISOString(),
    url: `https://x.com/${username}/status/${tweetId}`,
    conversation_id: stringValue(legacy?.conversation_id_str),
    lang: stringValue(legacy?.lang),
    media: normalizeMedia(legacy),
    quoted_tweet: normalizeReference(asObject(asObject(result.quoted_status_result)?.result)),
    reposted_tweet: normalizeReference(asObject(asObject(result.retweeted_status_result)?.result)),
    reply_to_tweet_id: stringValue(legacy?.in_reply_to_status_id_str),
    metrics: {
      like_count: numberValue(legacy?.favorite_count),
      repost_count: numberValue(legacy?.retweet_count),
      reply_count: numberValue(legacy?.reply_count),
      quote_count: numberValue(legacy?.quote_count),
      bookmark_count: numberValue(legacy?.bookmark_count),
      view_count: numberValue(asObject(result.views)?.count),
    },
    raw_payload: {
      typename: stringValue(result.__typename),
      has_note_tweet: Boolean(result.note_tweet),
    },
  };
}

function normalizeReference(value: JsonObject | undefined): XPostReference | null {
  const result = unwrapTweetResult(value);
  const legacy = asObject(result?.legacy);
  const user = asObject(asObject(asObject(result?.core)?.user_results)?.result);
  const userLegacy = asObject(user?.legacy);
  const tweetId = stringValue(result?.rest_id);
  const username = stringValue(userLegacy?.screen_name);
  if (!tweetId || !username) return null;
  return {
    tweet_id: tweetId,
    author_username: username,
    text: stringValue(legacy?.full_text) ?? "",
    url: `https://x.com/${username}/status/${tweetId}`,
  };
}

function normalizeMedia(legacy: JsonObject | undefined): XMedia[] {
  const extended = asObject(legacy?.extended_entities);
  const entries = Array.isArray(extended?.media) ? extended.media : [];
  const media: XMedia[] = [];
  for (const entry of entries) {
    const item = asObject(entry);
    const type = stringValue(item?.type);
    const preview = stringValue(item?.media_url_https);
    if (type === "photo" && preview) {
      media.push({type: "photo", url: preview, preview_url: preview});
      continue;
    }
    if ((type === "video" || type === "animated_gif") && preview) {
      const variants = Array.isArray(asObject(item?.video_info)?.variants)
        ? (asObject(item?.video_info)?.variants as unknown[])
        : [];
      const videoUrl = variants
        .map((variant) => asObject(variant))
        .filter((variant): variant is JsonObject => Boolean(variant))
        .filter((variant) => variant.content_type === "video/mp4")
        .sort((left, right) => (numberValue(right.bitrate) ?? 0) - (numberValue(left.bitrate) ?? 0))
        .map((variant) => stringValue(variant.url))
        .find((url): url is string => Boolean(url));
      media.push({type, url: videoUrl ?? preview, preview_url: preview});
    }
  }
  return media;
}

function unwrapTweetResult(value: unknown): JsonObject | undefined {
  const result = asObject(value);
  if (!result) return undefined;
  if (result.__typename === "TweetWithVisibilityResults") return asObject(result.tweet);
  return result;
}

function asObject(value: unknown): JsonObject | undefined {
  return isObject(value) ? value : undefined;
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}
