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
  const details = asObject(result.details);
  const counts = asObject(result.counts);
  const user = asObject(asObject(asObject(result.core)?.user_results)?.result);
  const userLegacy = asObject(user?.legacy) ?? asObject(user?.core);
  const tweetId = stringValue(result.rest_id);
  const username = stringValue(userLegacy?.screen_name);
  const createdAt = dateValue(legacy?.created_at ?? details?.created_at_ms);
  if (!tweetId || !username || !createdAt) return null;

  const publishedAt = new Date(createdAt);

  return {
    tweet_id: tweetId,
    author_id: stringValue(user?.rest_id),
    author_username: username,
    author_name: stringValue(userLegacy?.name),
    text: stringValue(legacy?.full_text ?? details?.full_text) ?? "",
    published_at: publishedAt.toISOString(),
    url: `https://x.com/${username}/status/${tweetId}`,
    conversation_id: stringValue(legacy?.conversation_id_str) ?? tweetId,
    lang: stringValue(legacy?.lang),
    media: normalizeMedia(result, legacy),
    quoted_tweet: normalizeReference(asObject(asObject(result.quoted_status_result)?.result)),
    reposted_tweet: normalizeReference(asObject(asObject(result.retweeted_status_result)?.result)),
    reply_to_tweet_id: stringValue(legacy?.in_reply_to_status_id_str),
    metrics: {
      like_count: numberValue(legacy?.favorite_count ?? counts?.favorite_count),
      repost_count: numberValue(legacy?.retweet_count ?? counts?.retweet_count),
      reply_count: numberValue(legacy?.reply_count ?? counts?.reply_count),
      quote_count: numberValue(legacy?.quote_count ?? counts?.quote_count),
      bookmark_count: numberValue(legacy?.bookmark_count ?? counts?.bookmark_count),
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

function normalizeMedia(result: JsonObject, legacy: JsonObject | undefined): XMedia[] {
  const extended = asObject(legacy?.extended_entities);
  const entries = Array.isArray(extended?.media)
    ? extended.media
    : Array.isArray(result.media_entities2)
      ? result.media_entities2
      : [];
  const media: XMedia[] = [];
  for (const entry of entries) {
    const item = asObject(entry);
    const type = stringValue(item?.type);
    const preview = stringValue(item?.media_url_https);
    const altText = stringValue(item?.ext_alt_text);
    if (type === "photo" && preview) {
      media.push({
        type: "photo",
        url: preview,
        preview_url: preview,
        ...(altText ? {alt_text: altText} : {}),
      });
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
      media.push({
        type,
        url: videoUrl ?? preview,
        preview_url: preview,
        ...(altText ? {alt_text: altText} : {}),
      });
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

function dateValue(value: unknown): string | number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return stringValue(value);
}
