import { describe, expect, it } from "vitest";

import { buildSourcePayload, SourcePayloadError } from "./sourcePayload";

describe("buildSourcePayload", () => {
  it("builds an SEC source with a mandatory CIK and default filing forms", () => {
    expect(
      buildSourcePayload({
        source_type: "sec_edgar",
        name: "NVIDIA SEC",
        cik: "0001045810",
        default_watchlist_ids: ["wl_nvda"],
      }),
    ).toMatchObject({
      source_type: "sec_edgar",
      config: { cik: "0001045810", forms: ["10-K", "10-Q", "8-K", "4"] },
      default_watchlist_ids: ["wl_nvda"],
      default_info_layer: "news",
      poll_interval_seconds: 3600,
    });
  });

  it("builds an account X web source with an opinion layer and 15-minute interval", () => {
    expect(
      buildSourcePayload({ source_type: "x_web", name: "NVIDIA X", x_username: "@nvidia" }),
    ).toMatchObject({
      source_type: "x_web",
      config: { mode: "account", username: "nvidia", max_items_per_poll: 50 },
      default_info_layer: "opinion",
      poll_interval_seconds: 900,
    });
  });

  it("rejects selected templates that lack their required configuration", () => {
    expect(() =>
      buildSourcePayload({ source_type: "sec_edgar", name: "NVIDIA SEC" }),
    ).toThrow(new SourcePayloadError("SEC EDGAR 需要填写 CIK"));
    expect(() =>
      buildSourcePayload({ source_type: "rss", name: "公司公告" }),
    ).toThrow(new SourcePayloadError("RSS / Atom 需要填写 URL"));
  });
});
