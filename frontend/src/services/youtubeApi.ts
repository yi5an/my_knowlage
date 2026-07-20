import { apiRequest, apiUrl } from "./client";

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

export interface OcrBlock {
  text: string;
  bbox: number[];
  confidence: number;
  reading_order?: number | null;
  region_type?: string | null;
}

export interface VisualMindmapTreeNode {
  title: string;
  children: VisualMindmapTreeNode[];
}

export interface VideoFrameAnalysis {
  id: string | null;
  timestamp_sec: number;
  timestamp_str: string;
  image_path: string;
  image_url: string | null;
  frame_type: "slide" | "mindmap" | "chart" | "table" | "screen_text" | "other";
  ocr_text: string;
  ocr_blocks: OcrBlock[];
  structured_notes: {
    title?: string;
    bullets?: string[];
    text?: string;
    tree?: VisualMindmapTreeNode;
    [key: string]: unknown;
  };
  confidence: number;
}

export interface VisualAnalysisRetryStatus {
  id: string;
  job_type: string;
  status: "pending" | "running" | "succeeded" | "failed";
  progress: number;
  output: Record<string, unknown>;
  error_message: string | null;
}

export interface SourceTraceCandidate {
  source_item_id: string;
  source_title: string;
  source_name: string | null;
  source_url: string | null;
  published_at: string | null;
  matched_fact: string;
  evidence_excerpt: string;
  lead_time_hours: number | null;
  confidence: number;
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
  knowledge_base_imported: boolean;
  channel_name: string | null;
  duration_sec: number | null;
  published_at: string | null;
  thumbnail_url: string | null;
  summary: SummaryResult | null;
  mindmap: MindmapData | null;
  transcript: string | null;
  visual_frames: VideoFrameAnalysis[];
  source_traces: SourceTraceCandidate[];
  local_video_status: string;
  local_video_url: string | null;
  local_video_size: number | null;
  local_video_error: string | null;
}

export interface LocalVideoDownloadResponse {
  video_id: string;
  status: string;
  task_job_id: string | null;
  local_video_url: string | null;
  local_video_size: number | null;
  error: string | null;
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

export interface YouTubeAutoRetrySettings {
  workspace_id: string;
  enabled: boolean;
  max_attempts: number;
  backoff_minutes: number;
  batch_size: number;
}

// --- API calls ---

export function youtubeTimestampUrl(videoId: string, timestamp: number): string {
  return `https://youtu.be/${videoId}?t=${Math.round(timestamp)}`;
}

export function youtubeThumbnailUrl(videoId: string | null | undefined): string | null {
  if (!videoId) return null;
  return apiUrl(`/youtube/videos/${encodeURIComponent(videoId)}/thumbnail`);
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

export function updateVisualFrameMindmap(
  frameId: string,
  tree: VisualMindmapTreeNode,
): Promise<VideoFrameAnalysis> {
  return apiRequest<VideoFrameAnalysis>(`/youtube/visual-frames/${frameId}/mindmap`, {
    method: "PUT",
    body: { tree },
  });
}

export function retryVisualAnalysis(videoId: string): Promise<VisualAnalysisRetryStatus> {
  return apiRequest<VisualAnalysisRetryStatus>(
    `/youtube/videos/${encodeURIComponent(videoId)}/visual-analysis/retry`,
    { method: "POST" },
  );
}

export function getVisualAnalysisStatus(videoId: string): Promise<VisualAnalysisRetryStatus | null> {
  return apiRequest<VisualAnalysisRetryStatus | null>(
    `/youtube/videos/${encodeURIComponent(videoId)}/visual-analysis/status`,
  );
}

export function downloadLocalVideo(videoId: string): Promise<LocalVideoDownloadResponse> {
  return apiRequest<LocalVideoDownloadResponse>(
    `/youtube/videos/${encodeURIComponent(videoId)}/local-video/download`,
    { method: "POST" },
  );
}

export function importSummaryToKnowledgeBase(
  documentId: string,
): Promise<VideoSummaryCard> {
  return apiRequest<VideoSummaryCard>(
    `/youtube/summaries/${documentId}/import-to-knowledge-base`,
    { method: "POST" },
  );
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
  status:
    | "processing"
    | "unknown"
    | "succeeded"
    | "no_transcript"
    | "failed"
    | "access_denied";
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
    if (status.status === "access_denied") {
      throw new Error(
        "该视频无访问权限（会员专属/私有/已删除/地区受限），已跳过。",
      );
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

export function getAutoRetrySettings(
  workspaceId = "ws_default",
): Promise<YouTubeAutoRetrySettings> {
  return apiRequest<YouTubeAutoRetrySettings>(
    `/youtube/auto-retry-settings?workspace_id=${workspaceId}`,
  );
}

export function updateAutoRetrySettings(
  settings: Omit<YouTubeAutoRetrySettings, "workspace_id">,
  workspaceId = "ws_default",
): Promise<YouTubeAutoRetrySettings> {
  return apiRequest<YouTubeAutoRetrySettings>(
    `/youtube/auto-retry-settings?workspace_id=${workspaceId}`,
    { method: "PUT", body: settings },
  );
}

export interface DashboardStats {
  subscriptions: number;
  summarized_videos: number;
  pending_videos: number;
  /** Permanently inaccessible videos (members-only / private / deleted / geo-blocked). */
  denied_videos: number;
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
  summary_status: "pending" | "processing" | "completed" | "failed" | string;
  error: string | null;
  failure_stage?: "capture" | "transcript" | "summary" | "pending" | "processing" | null;
  retryable?: boolean;
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

export function retryVideo(
  videoId: string,
  workspaceId = "ws_default",
): Promise<ManualSummaryResponse> {
  return apiRequest<ManualSummaryResponse>(
    `/youtube/videos/${videoId}/retry?workspace_id=${workspaceId}`,
    { method: "POST" },
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
