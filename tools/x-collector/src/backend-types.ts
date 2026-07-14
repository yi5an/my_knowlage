export interface XCollectorHeartbeat {
  collector_id: string;
  version: string;
  login_status: "uninitialized" | "ready" | "auth_required" | "challenge_required";
  queue_size: number;
  last_success_at?: string;
  last_error?: string;
}

export interface XCollectorCommandResponse {
  job_id: string;
  source_id: string;
  workspace_id: string;
  name: string;
  mode: "account" | "keyword";
  config: Record<string, unknown>;
  poll_interval_seconds: number;
}

export interface XCollectorCommandComplete {
  status: "succeeded" | "failed";
  items_seen: number;
  items_created: number;
  items_updated: number;
  items_skipped: number;
  error?: string;
}
