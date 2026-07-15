import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestmentThemesPage } from "./InvestmentThemesPage";

describe("InvestmentThemesPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows theme-first tracking domains", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/investment/themes")) {
          return new Response(
            JSON.stringify([
              {
                id: "theme_ai",
                workspace_id: "ws_default",
                name: "AI 算力",
                description: "GPU, HBM, data center power",
                theme_type: "sector",
                keywords: ["HBM", "数据中心电力"],
                entities: ["NVDA", "AMD"],
                tickers: ["NVDA", "AMD"],
                enabled: true,
                priority: "high",
              },
            ]),
            { status: 200 },
          );
        }
        return new Response("not found", { status: 404 });
      }),
    );

    render(
      <MemoryRouter>
        <InvestmentThemesPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("主题中心")).toBeInTheDocument();
    expect(screen.getByText("AI 算力")).toBeInTheDocument();
    expect(screen.getByText("HBM")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });
});
