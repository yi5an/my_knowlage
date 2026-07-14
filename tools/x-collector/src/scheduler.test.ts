import { describe, expect, it } from "vitest";

import { CollectorSessionError } from "./session.js";
import { classifyRetry, withRetry } from "./scheduler.js";

describe("withRetry", () => {
  it("retries transient failures with bounded attempts", async () => {
    let attempts = 0;
    const result = await withRetry(async () => {
      attempts += 1;
      if (attempts < 3) throw new CollectorSessionError("network_error", "offline");
      return "ok";
    }, {sleep: async () => {}});

    expect(result).toBe("ok");
    expect(attempts).toBe(3);
  });

  it("does not retry authentication failures", async () => {
    let attempts = 0;
    await expect(
      withRetry(async () => {
        attempts += 1;
        throw new CollectorSessionError("auth_required", "login required");
      }, {sleep: async () => {}}),
    ).rejects.toThrow("login required");
    expect(attempts).toBe(1);
  });
});

describe("classifyRetry", () => {
  it("retries network and rate-limit errors only", () => {
    expect(classifyRetry(new CollectorSessionError("network_error", "offline")).retry).toBe(true);
    expect(classifyRetry(new CollectorSessionError("rate_limited", "slow")).retry).toBe(true);
    expect(classifyRetry(new CollectorSessionError("auth_required", "login")).retry).toBe(false);
  });
});
