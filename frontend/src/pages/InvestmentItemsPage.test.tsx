import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InvestmentItemsPage } from "./InvestmentItemsPage";

function renderPage() {
  render(
    <MemoryRouter>
      <InvestmentItemsPage />
    </MemoryRouter>,
  );
}

describe("InvestmentItemsPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/items")) {
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

  it("renders the heading and real empty state", async () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "投资信息" })).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText("暂无投资信息（创建数据源并抓取后会出现真实条目）"),
      ).toBeInTheDocument();
    });
  });
});
