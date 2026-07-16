export interface XMedia {
  type: "photo" | "video" | "animated_gif";
  url: string;
  preview_url?: string;
  alt_text?: string;
}

export interface XPostReference {
  tweet_id: string;
  author_username: string;
  text: string;
  url: string;
}

export interface XPostMetrics {
  like_count: number | null;
  repost_count: number | null;
  reply_count: number | null;
  quote_count: number | null;
  bookmark_count: number | null;
  view_count: number | null;
}

export interface XPost {
  tweet_id: string;
  author_id: string | null;
  author_username: string;
  author_name: string | null;
  text: string;
  published_at: string;
  url: string;
  conversation_id: string | null;
  lang: string | null;
  media: XMedia[];
  quoted_tweet: XPostReference | null;
  reposted_tweet: XPostReference | null;
  reply_to_tweet_id: string | null;
  metrics: XPostMetrics;
  raw_payload: Record<string, unknown>;
}

export type JsonObject = Record<string, unknown>;
