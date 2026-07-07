import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "./client";

describe("apiRequest", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses nested backend error message when detail is absent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            error: {
              code: "translation_failed",
              message: "investment translation failed",
            },
          }),
          { status: 502 },
        ),
      ),
    );

    await expect(apiRequest("/investment/items/translate")).rejects.toMatchObject({
      name: "ApiError",
      message: "investment translation failed",
      status: 502,
    });
  });
});
