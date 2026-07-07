import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InvestmentDashboardPage } from "./InvestmentDashboardPage";

function renderPage() {
  render(
    <MemoryRouter>
      <InvestmentDashboardPage />
    </MemoryRouter>,
  );
}

describe("InvestmentDashboardPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.includes("/investment/dashboard")) {
          return new Response(
            JSON.stringify({
              pending_review_count: 3,
              pending_claims_count: 1,
              theses_challenged_count: 0,
              today_primary_count: 2,
              today_macro_count: 1,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
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

  it("renders the page heading", async () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "投资工作台" })).toBeInTheDocument();
  });

  it("shows real dashboard counts from the API (no sample data)", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("3")).toBeInTheDocument(); // pending_review_count
    });
    expect(screen.getByText("今日待处理")).toBeInTheDocument();
    // "1" appears for both pending_claims_count and today_macro_count
    expect(screen.getAllByText("1").length).toBeGreaterThanOrEqual(2);
  });

  it("shows an empty state for pending items when the list is empty", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("暂无待处理信息")).toBeInTheDocument();
    });
  });
});
