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

  it("saves pasted YouTube cookies without retaining the secret input", async () => {
    const cookieText = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsecret-value";
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/youtube/auto-retry-settings") && init?.method === "GET") {
        return Response.json({ workspace_id: "ws_default", enabled: false, max_attempts: 3, backoff_minutes: 30, batch_size: 1 });
      }
      if (url.endsWith("/youtube/cookies") && init?.method === "GET") {
        return Response.json({ configured: false, updated_at: null, file_size: null, validation_status: "not_configured" });
      }
      if (url.endsWith("/youtube/cookies") && init?.method === "PUT") {
        return Response.json({ configured: true, updated_at: "2026-08-12T00:00:00Z", file_size: 88, validation_status: "valid" });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "替换 Cookie" }));
    fireEvent.change(screen.getByLabelText("YouTube Cookie 文本"), { target: { value: cookieText } });
    fireEvent.click(screen.getByRole("button", { name: "保存并校验" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/youtube/cookies",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ cookies_text: cookieText }) }),
    ));
    expect(screen.queryByLabelText("YouTube Cookie 文本")).not.toBeInTheDocument();
    expect(await screen.findByText("Cookie 已配置")).toBeInTheDocument();
  });

  it("shows the scrubbed result of testing a configured YouTube cookie", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/youtube/auto-retry-settings") && init?.method === "GET") {
        return Response.json({ workspace_id: "ws_default", enabled: false, max_attempts: 3, backoff_minutes: 30, batch_size: 1 });
      }
      if (url.endsWith("/youtube/cookies") && init?.method === "GET") {
        return Response.json({ configured: true, updated_at: "2026-08-12T00:00:00Z", file_size: 88, validation_status: "valid" });
      }
      if (url.endsWith("/youtube/cookies/test") && init?.method === "POST") {
        return Response.json({ success: true, status: "ok", message: "Cookie 可用于 YouTube。" });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "测试当前 Cookie" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/youtube/cookies/test",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(await screen.findByText("Cookie 可用于 YouTube。")).toBeInTheDocument();
  });

  it("removes a configured YouTube cookie only after confirmation", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/youtube/auto-retry-settings") && init?.method === "GET") {
        return Response.json({ workspace_id: "ws_default", enabled: false, max_attempts: 3, backoff_minutes: 30, batch_size: 1 });
      }
      if (url.endsWith("/youtube/cookies") && init?.method === "GET") {
        return Response.json({ configured: true, updated_at: "2026-08-12T00:00:00Z", file_size: 88, validation_status: "valid" });
      }
      if (url.endsWith("/youtube/cookies") && init?.method === "DELETE") {
        return Response.json({ configured: false, updated_at: null, file_size: null, validation_status: "not_configured" });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SettingsPage />);

    await screen.findByText("Cookie 已配置");
    fireEvent.click(await screen.findByRole("button", { name: "移除 Cookie" }));
    fireEvent.click(await screen.findByRole("button", { name: "OK" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/youtube/cookies",
      expect.objectContaining({ method: "DELETE" }),
    ));
    expect(await screen.findByText("未配置 Cookie")).toBeInTheDocument();
  });
});
