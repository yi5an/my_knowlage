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
        if (u.includes("/investment/sources")) {
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
});
