import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "./SettingsPage";

describe("SettingsPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("saves YouTube automatic retry settings", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/youtube/auto-retry-settings") && !init) {
        return Response.json({
          workspace_id: "ws_default",
          enabled: false,
          max_attempts: 3,
          backoff_minutes: 30,
          batch_size: 1,
        });
      }
      if (url.includes("/youtube/auto-retry-settings") && init?.method === "PUT") {
        return Response.json({
          workspace_id: "ws_default",
          enabled: true,
          max_attempts: 3,
          backoff_minutes: 30,
          batch_size: 1,
        });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SettingsPage />);

    const toggle = await screen.findByRole("switch", { name: "启用自动重试" });
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: "保存自动重试配置" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/youtube/auto-retry-settings?workspace_id=ws_default"),
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            enabled: true,
            max_attempts: 3,
            backoff_minutes: 30,
            batch_size: 1,
          }),
        }),
      );
    });
    expect(await screen.findByText("已保存")).toBeInTheDocument();
  });
});
