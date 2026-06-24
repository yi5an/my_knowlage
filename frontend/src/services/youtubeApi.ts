import { apiRequest } from "./client";

// --- Types matching backend app/schemas/youtube.py ---

export interface KeyPoint {
  point: string;
  timestamp: number;
  timestamp_str: string;
}

export interface Quote {
  text: string;
  timestamp: number;
  timestamp_str: string;
}

export interface Chapter {
  title: string;
  start_sec: number;
  start_str: string;
}

export interface SummaryResult {
  tldr: string;
  key_points: KeyPoint[];
  quotes: Quote[];
  chapters: Chapter[];
  tags: string[];
  transcript_source: "manual" | "auto";
}

export interface MindmapNode {
  title: string;
  timestamp?: number | null;
  timestamp_str?: string | null;
  children: MindmapNode[];
}

export interface MindmapData {
  root_title: string;
  children: MindmapNode[];
}

export interface VideoSummaryCard {
  document_id: string;
  video_id: string;
  title: string;
  channel_name: string | null;
  duration_sec: number | null;
  published_at: string | null;
  thumbnail_url: string | null;
  summary: SummaryResult | null;
  mindmap: MindmapData | null;
  transcript: string | null;
}

export interface Subscription {
  id: string;
  workspace_id: string;
  platform: string;
  channel_id: string;
  channel_name: string | null;
  thumbnail_url: string | null;
  poll_interval: number;
  last_polled_at: string | null;
  next_poll_at: string | null;
  last_video_id: string | null;
  last_error: string | null;
  enabled: boolean;
}

export interface ManualSummaryResponse {
  video_id: string;
  document_id: string;
  task_job_id: string;
  status: string;
}

export interface PollResponse {
  poll_count: number;
  /** Number of newly-discovered videos (summarized async in the background). */
  discovered: number;
  videos: { video_id: string; title: string; channel_id: string }[];
}

// --- API calls ---

export function youtubeTimestampUrl(videoId: string, timestamp: number): string {
  return `https://youtu.be/${videoId}?t=${Math.round(timestamp)}`;
}

export function summarizeVideo(
  url: string,
  workspaceId = "ws_default",
  preferredLanguage?: string,
): Promise<ManualSummaryResponse> {
  return apiRequest<ManualSummaryResponse>("/youtube/summarize", {
    method: "POST",
    body: { url, workspace_id: workspaceId, preferred_language: preferredLanguage },
  });
}

export function getSummaryCard(documentId: string): Promise<VideoSummaryCard> {
  return apiRequest<VideoSummaryCard>(`/youtube/summaries/${documentId}`);
}

/**
 * Background job status returned by the by-video poll endpoint.
 *  - processing: ASR/translation/summary pipeline still running
 *  - unknown:    backend hasn't fetched+upserted the Video row yet (warming up)
 *  - succeeded:  done — `documentId` is set, fetch the full card
 *  - no_transcript / failed: terminal error, `error` holds the message
 */
export interface SummaryJobStatus {
  video_id: string;
  status: "processing" | "unknown" | "succeeded" | "no_transcript" | "failed";
  document_id?: string | null;
  error?: string | null;
}

export function getSummaryStatusByVideo(videoId: string): Promise<SummaryJobStatus> {
  return apiRequest<SummaryJobStatus>(`/youtube/summaries/by-video/${videoId}`);
}

/**
 * Poll the by-video status endpoint until the background job reaches a
 * terminal state. Resolves with the finished documentId on success, or
 * rejects with the server error message on failure/timeout.
 *
 * ASR on a long video can take several minutes, so the default timeout is
 * generous (15 min) and the interval starts at 1.5s.
 */
export async function pollSummaryUntilDone(
  videoId: string,
  opts: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<string> {
  const intervalMs = opts.intervalMs ?? 1500;
  const timeoutMs = opts.timeoutMs ?? 15 * 60 * 1000;
  const deadline = Date.now() + timeoutMs;
  // First poll is slightly longer to give the backend a moment to upsert.
  await new Promise((r) => setTimeout(r, 400));
  while (Date.now() < deadline) {
    const status = await getSummaryStatusByVideo(videoId);
    if (status.status === "succeeded" && status.document_id) {
      return status.document_id;
    }
    if (status.status === "failed") {
      throw new Error(status.error || "总结失败,请稍后重试。");
    }
    if (status.status === "no_transcript") {
      throw new Error("该视频没有字幕,且未启用语音识别(ASR),无法总结。");
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("总结超时,请稍后刷新查看。");
}

export function listSubscriptions(workspaceId = "ws_default"): Promise<Subscription[]> {
  return apiRequest<Subscription[]>(`/youtube/subscriptions?workspace_id=${workspaceId}`);
}

export function createSubscription(
  channelId: string,
  opts: { channelName?: string; pollInterval?: number; workspaceId?: string } = {},
): Promise<Subscription> {
  return apiRequest<Subscription>("/youtube/subscriptions", {
    method: "POST",
    body: {
      channel_id: channelId,
      channel_name: opts.channelName,
      poll_interval: opts.pollInterval ?? 3600,
      workspace_id: opts.workspaceId ?? "ws_default",
    },
  });
}

export function deleteSubscription(subscriptionId: string): Promise<void> {
  return apiRequest<void>(`/youtube/subscriptions/${subscriptionId}`, { method: "DELETE" });
}

export function triggerPoll(workspaceId = "ws_default"): Promise<PollResponse> {
  return apiRequest<PollResponse>(`/youtube/poll?workspace_id=${workspaceId}`, { method: "POST" });
}

export interface DashboardStats {
  subscriptions: number;
  summarized_videos: number;
  pending_videos: number;
  entities: number;
  relations: number;
}

export interface SummaryListItem {
  document_id: string;
  video_id: string;
  title: string;
  channel_name: string | null;
  thumbnail_url: string | null;
  duration_sec: number | null;
  published_at: string | null;
  tldr: string | null;
  tags: string[];
  created_at: string | null;
  /** True until the user opens this summary's card (shows a star). */
  is_unread: boolean;
}

export function getDashboardStats(workspaceId = "ws_default"): Promise<DashboardStats> {
  return apiRequest<DashboardStats>(`/youtube/stats?workspace_id=${workspaceId}`);
}

export function listSummaries(
  workspaceId = "ws_default",
  limit = 20,
): Promise<SummaryListItem[]> {
  return apiRequest<SummaryListItem[]>(
    `/youtube/summaries?workspace_id=${workspaceId}&limit=${limit}`,
  );
}

/**
 * Mark a summary as read (removes the unread star). Called when the user
 * opens the card page. Fire-and-forget — failures are non-fatal (the star
 * is purely a visual hint).
 */
export function markSummaryRead(documentId: string): Promise<void> {
  return apiRequest<void>(`/youtube/summaries/${documentId}/mark-read`, {
    method: "POST",
  });
}
