import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InvestmentSourcesPage } from "./InvestmentSourcesPage";

function renderPage() {
  render(
    <MemoryRouter>
      <InvestmentSourcesPage />
    </MemoryRouter>,
  );
}

describe("InvestmentSourcesPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/watchlist")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/sources")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/x-collector/states")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response("not found", { status: 404 });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders heading, add button and the empty state", async () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "数据源" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新增数据源" })).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText("暂无数据源。创建一个 SEC 或 RSS 数据源后点击「立即抓取」。"),
      ).toBeInTheDocument();
    });
  });

  it("offers X RSSHub and Nitter source types", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "新增数据源" }));
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "类型" }));

    expect(await screen.findByText("X / RSSHub（公开推文）")).toBeInTheDocument();
    expect(screen.getByText("X / Nitter 镜像（公开推文）")).toBeInTheDocument();
  });

  it("offers Bright Data X source type for high frequency collection", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "新增数据源" }));
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "类型" }));
    fireEvent.click(await screen.findByText("X / Bright Data（账号高频采集）"));

    expect(screen.getByLabelText("X 账号 URL（每行一个）")).toBeInTheDocument();
    expect(screen.getByLabelText("抓取频率(秒)")).toHaveValue("21600");
  });

  it("offers X Web account and keyword modes with different defaults", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "新增数据源" }));
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "类型" }));
    fireEvent.click(await screen.findByText("X / 网页采集"));

    expect(screen.getByRole("combobox", { name: "采集模式" })).toBeInTheDocument();
    expect(screen.getByLabelText("X 用户名")).toBeInTheDocument();
    expect(screen.getByLabelText("抓取频率(秒)")).toHaveValue("900");

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "采集模式" }));
    fireEvent.click(await screen.findByText("关键词主题"));

    expect(screen.getByLabelText("关键词")).toBeInTheDocument();
    expect(screen.queryByLabelText("X 用户名")).not.toBeInTheDocument();
    expect(screen.getByLabelText("抓取频率(秒)")).toHaveValue("1800");
  });

  it("shows the X collector login status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/watchlist")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (u.includes("/investment/sources")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response(
          JSON.stringify([
            {
              collector_id: "macbook",
              version: "0.1.0",
              login_status: "auth_required",
              queue_size: 0,
              heartbeat_at: "2026-07-14T00:00:00Z",
            },
          ]),
          { status: 200 },
        );
      }),
    );

    renderPage();

    expect(await screen.findByText("X 网页采集器：需要重新登录")).toBeInTheDocument();
  });

  it("shows source watchlist binding labels", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/watchlist")) {
          return new Response(
            JSON.stringify([
              {
                id: "wl_nvda",
                workspace_id: "ws_default",
                name: "NVIDIA",
                watch_type: "company",
                keywords: [],
                importance: "high",
                enabled: true,
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/sources")) {
          return new Response(
            JSON.stringify([
              {
                id: "src_nvda",
                workspace_id: "ws_default",
                source_type: "x_web",
                name: "NVIDIA X",
                config: { mode: "account", username: "nvidia" },
                default_info_layer: "opinion",
                default_watchlist_ids: ["wl_nvda"],
                poll_interval_seconds: 900,
                enabled: true,
              },
            ]),
            { status: 200 },
          );
        }
        if (u.includes("/investment/x-collector/states")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    expect(await screen.findByText("NVIDIA X")).toBeInTheDocument();
    expect(screen.getByText("NVIDIA")).toBeInTheDocument();
  });

  it("creates default X sources from the sources page", async () => {
    let defaultsCreated = false;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/investment/sources/defaults") && init?.method === "POST") {
        defaultsCreated = true;
        return new Response(
          JSON.stringify([
            {
              id: "src_potus",
              workspace_id: "ws_default",
              source_type: "x_web",
              name: "POTUS 官方",
              config: { mode: "account", username: "POTUS" },
              default_info_layer: "opinion",
              default_watchlist_ids: [],
              poll_interval_seconds: 900,
              enabled: true,
            },
          ]),
          { status: 201 },
        );
      }
      if (u.includes("/investment/watchlist")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (u.includes("/investment/sources")) {
        return new Response(
          JSON.stringify(
            defaultsCreated
              ? [
                  {
                    id: "src_potus",
                    workspace_id: "ws_default",
                    source_type: "x_web",
                    name: "POTUS 官方",
                    config: { mode: "account", username: "POTUS" },
                    default_info_layer: "opinion",
                    default_watchlist_ids: [],
                    poll_interval_seconds: 900,
                    enabled: true,
                  },
                ]
              : [],
          ),
          { status: 200 },
        );
      }
      if (u.includes("/investment/x-collector/states")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "创建默认 X 源" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/investment/sources/defaults"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(await screen.findByText("POTUS 官方")).toBeInTheDocument();
  });
});
