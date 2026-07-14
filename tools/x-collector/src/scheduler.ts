import { CollectorSessionError } from "./session.js";

export interface RetryDecision {
  retry: boolean;
  retryAfterMs?: number;
}

export function classifyRetry(error: unknown): RetryDecision {
  if (!(error instanceof CollectorSessionError)) return {retry: true};
  if (error.code === "auth_required" || error.code === "challenge_required") {
    return {retry: false};
  }
  return {retry: true, retryAfterMs: error.retryAfterMs};
}

export async function withRetry<T>(
  operation: () => Promise<T>,
  options: {maxAttempts?: number; sleep?: (milliseconds: number) => Promise<void>} = {},
): Promise<T> {
  const maxAttempts = options.maxAttempts ?? 5;
  const sleep = options.sleep ?? ((milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)));
  let lastError: unknown;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      const decision = classifyRetry(error);
      if (!decision.retry || attempt === maxAttempts - 1) throw error;
      await sleep(decision.retryAfterMs ?? Math.min(60_000, 1_000 * 2 ** attempt));
    }
  }
  throw lastError ?? new Error("retry failed");
}
