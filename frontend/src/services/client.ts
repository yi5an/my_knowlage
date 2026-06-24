const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export type ApiRequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      method: options.method ?? "GET",
      headers: {
        "Content-Type": "application/json",
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    // Network failure / timeout — the backend is unreachable.
    throw new ApiError("无法连接到后端服务，请确认服务正在运行或网络正常。", 0);
  }

  if (!response.ok) {
    // Try to extract the backend's Chinese detail message.
    const text = await response.text().catch(() => "");
    let detail = `请求失败（${response.status}）`;
    if (text) {
      try {
        const parsed = JSON.parse(text);
        const msg = parsed?.error?.detail ?? parsed?.detail ?? parsed?.message;
        if (typeof msg === "string" && msg) detail = msg;
      } catch {
        if (text.length < 200) detail = text;
      }
    }
    throw new ApiError(detail, response.status);
  }

  // 204 No Content (e.g. DELETE) or an empty body has no JSON to parse.
  if (response.status === 204) {
    return undefined as T;
  }
  const body = await response.text();
  if (!body) {
    return undefined as T;
  }
  return JSON.parse(body) as T;
}

