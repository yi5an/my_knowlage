import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestmentDigestPage } from "./InvestmentDigestPage";

function renderPage() {
  render(
    <MemoryRouter>
      <InvestmentDigestPage />
    </MemoryRouter>,
  );
}

describe("InvestmentDigestPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows early signals and pending facts from the digest API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/investment/digest")) {
          if (String(url).includes("/investment/digest/snapshots")) {
            return new Response(JSON.stringify([]), { status: 200 });
          }
          return new Response(
            JSON.stringify({
              counts: {
                pending_review_count: 1,
                pending_claims_count: 1,
                theses_challenged_count: 0,
                today_primary_count: 0,
                today_macro_count: 0,
              },
              today_highlights: [],
              pending_claims: [],
              challenged_items: [],
              early_signals: [
                {
                  id: "sig_digest",
                  workspace_id: "ws_default",
                  title: "NVIDIA / company_update",
                  summary: "英伟达宣布了一个平台。",
                  signal_type: "company_update",
                  first_seen_at: "2026-07-15T00:00:00Z",
                  last_seen_at: "2026-07-15T01:00:00Z",
                  source_count: 1,
                  fact_ids: ["fact_digest"],
                  item_ids: ["inv_digest"],
                  confidence: 0.8,
                  status: "tracking",
                },
              ],
              pending_facts: [
                {
                  id: "fact_digest",
                  workspace_id: "ws_default",
                  source_item_id: "inv_digest",
                  fact_text: "NVIDIA announced a platform.",
                  fact_text_zh: "英伟达宣布了一个平台。",
                  fact_type: "company_update",
                  entities: ["NVIDIA"],
                  evidence_url: "https://x.com/nvidia/status/1",
                  evidence_excerpt: "NVIDIA platform",
                  confidence: 0.8,
                  verification_status: "pending",
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (String(url).includes("/investment/watchlist")) {
          return new Response(
            JSON.stringify([
              {
                id: "wl_ai",
                workspace_id: "ws_default",
                name: "AI Infra",
                watch_type: "theme",
                keywords: [],
                importance: "high",
                enabled: true,
              },
            ]),
            { status: 200 },
          );
        }
        return new Response("not found", { status: 404 });
      }),
    );

    renderPage();

    expect(await screen.findByText("NVIDIA / company_update")).toBeInTheDocument();
    expect(screen.getAllByText("英伟达宣布了一个平台。").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("证据：NVIDIA platform")).toBeInTheDocument();
    expect(screen.getAllByText("置信度 80%").length).toBeGreaterThanOrEqual(1);
  });

  it("requests digest scoped to selected watchlist", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/investment/digest/snapshots")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (u.includes("/investment/digest")) {
        return new Response(
          JSON.stringify({
            counts: {
              pending_review_count: 0,
              pending_claims_count: 0,
              theses_challenged_count: 0,
              today_primary_count: 0,
              today_macro_count: 0,
            },
            today_highlights: [],
            pending_claims: [],
            challenged_items: [],
            early_signals: [],
            pending_facts: [],
          }),
          { status: 200 },
        );
      }
      if (u.includes("/investment/watchlist")) {
        return new Response(
          JSON.stringify([
            {
              id: "wl_ai",
              workspace_id: "ws_default",
              name: "AI Infra",
              watch_type: "theme",
              keywords: [],
              importance: "high",
              enabled: true,
            },
          ]),
          { status: 200 },
        );
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.mouseDown(await screen.findByRole("combobox"));
    fireEvent.click(await screen.findByText("AI Infra"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("watchlist_id=wl_ai"),
        expect.anything(),
      );
    });
  });

  it("saves a digest snapshot and reloads snapshot history", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/investment/digest/snapshots") && init?.method === "POST") {
        return new Response(
          JSON.stringify({
            id: "dig_1",
            workspace_id: "ws_default",
            digest_date: "2026-07-15T00:00:00Z",
            title: "每日简报",
            digest: {
              counts: {
                pending_review_count: 0,
                pending_claims_count: 0,
                theses_challenged_count: 0,
                today_primary_count: 0,
                today_macro_count: 0,
              },
              today_highlights: [],
              pending_claims: [],
              challenged_items: [],
              early_signals: [],
              pending_facts: [],
            },
          }),
          { status: 201 },
        );
      }
      if (u.includes("/investment/digest/snapshots")) {
        return new Response(
          JSON.stringify([
            {
              id: "dig_1",
              workspace_id: "ws_default",
              digest_date: "2026-07-15T00:00:00Z",
              title: "每日简报",
              digest: {
                counts: {
                  pending_review_count: 0,
                  pending_claims_count: 0,
                  theses_challenged_count: 0,
                  today_primary_count: 0,
                  today_macro_count: 0,
                },
                today_highlights: [],
                pending_claims: [],
                challenged_items: [],
                early_signals: [],
                pending_facts: [],
              },
            },
          ]),
          { status: 200 },
        );
      }
      if (u.includes("/investment/digest")) {
        return new Response(
          JSON.stringify({
            counts: {
              pending_review_count: 0,
              pending_claims_count: 0,
              theses_challenged_count: 0,
              today_primary_count: 0,
              today_macro_count: 0,
            },
            today_highlights: [],
            pending_claims: [],
            challenged_items: [],
            early_signals: [],
            pending_facts: [],
          }),
          { status: 200 },
        );
      }
      if (u.includes("/investment/watchlist")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "保存快照" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/investment/digest/snapshots"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => {
      expect(screen.getAllByText("每日简报").length).toBeGreaterThanOrEqual(2);
    });
  });
});
