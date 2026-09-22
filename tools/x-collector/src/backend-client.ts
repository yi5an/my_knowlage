import type { XCollectorCommandComplete, XCollectorCommandResponse, XCollectorHeartbeat } from "./backend-types.js";
import type { XPost } from "./types.js";

export interface XPostImportResponse {
  items_seen: number;
  items_created: number;
  items_updated: number;
  items_skipped: number;
  errors: Array<Record<string, unknown>>;
}

type FetchImplementation = typeof fetch;

export class BackendClientError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "BackendClientError";
  }
}

export class BackendClient {
  private readonly baseUrl: string;

  constructor(
    baseUrl: string,
    private readonly token: string | undefined,
    private readonly fetchImpl: FetchImplementation = fetch,
  ) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  async importPosts(sourceId: string, collectorId: string, posts: XPost[]): Promise<XPostImportResponse> {
    return this.request<XPostImportResponse>("/api/v1/investment/import/x-posts", {
      method: "POST",
      body: JSON.stringify({
        source_id: sourceId,
        collector_id: collectorId,
        items: posts,
      }),
    });
  }

  async heartbeat(payload: XCollectorHeartbeat): Promise<unknown> {
    return this.request("/api/v1/investment/x-collector/heartbeat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async claimCommands(collectorId: string): Promise<XCollectorCommandResponse[]> {
    return this.request<XCollectorCommandResponse[]>(
      `/api/v1/investment/x-collector/commands?collector_id=${encodeURIComponent(collectorId)}`,
    );
  }

  async completeCommand(jobId: string, payload: XCollectorCommandComplete): Promise<unknown> {
    return this.request(`/api/v1/investment/x-collector/commands/${jobId}/complete`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("content-type", "application/json");
    if (this.token) headers.set("authorization", `Bearer ${this.token}`);
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {...init, headers});
    const body = (await response.json().catch(() => null)) as unknown;
    if (!response.ok) {
      const errorBody = isObject(body) ? body.error : undefined;
      let message = `KnowPilot API failed with ${response.status}`;
      if (isObject(errorBody) && typeof errorBody.message === "string") {
        message = errorBody.message;
      }
      // FastAPI validation payloads keep field-level detail in error.details
      // (or bare detail); surface it so failed imports name the offending field.
      const details = isObject(errorBody) ? errorBody.details : undefined;
      const detail = isObject(body) ? body.detail : undefined;
      const extra =
        details ?? (Array.isArray(detail) || typeof detail === "string" ? detail : undefined);
      if (extra !== undefined && extra !== null) {
        message += `: ${JSON.stringify(extra).slice(0, 300)}`;
      }
      throw new BackendClientError(response.status, message);
    }
    return body as T;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
