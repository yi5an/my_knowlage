import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestmentClaimsPage } from "./InvestmentClaimsPage";

function renderPage() {
  render(
    <MemoryRouter>
      <InvestmentClaimsPage />
    </MemoryRouter>,
  );
}

describe("InvestmentClaimsPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("lets the user refute a pending claim without running evidence search", async () => {
    let status: "pending" | "refuted" = "pending";
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/investment/claims/cl_1/status") && init?.method === "POST") {
        status = "refuted";
        return new Response(
          JSON.stringify({
            id: "cl_1",
            workspace_id: "ws_default",
            claim_text: "Data center revenue doubles",
            required_evidence: ["10-K segment data"],
            verification_status: "refuted",
            verification_summary: "人工证伪",
            evidence_doc_ids: [],
          }),
          { status: 200 },
        );
      }
      if (u.includes("/investment/claims")) {
        return new Response(
          JSON.stringify([
            {
              id: "cl_1",
              workspace_id: "ws_default",
              claim_text: "Data center revenue doubles",
              required_evidence: ["10-K segment data"],
              verification_status: status,
              verification_summary: status === "refuted" ? "人工证伪" : null,
              evidence_doc_ids: [],
            },
          ]),
          { status: 200 },
        );
      }
      if (u.includes("/investment/watchlist")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (u.includes("/investment/theses")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("Data center revenue doubles")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /证\s*伪/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/investment/claims/cl_1/status"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            verification_status: "refuted",
            verification_summary: "人工标记为已证伪",
          }),
        }),
      );
    });
    expect(await screen.findByText("已证伪")).toBeInTheDocument();
  });

  it("links an existing claim to a thesis from the list", async () => {
    let thesisId: string | null = null;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/investment/claims/cl_1/status") && init?.method === "POST") {
        thesisId = JSON.parse(String(init.body)).thesis_id;
        return new Response(
          JSON.stringify({
            id: "cl_1",
            workspace_id: "ws_default",
            claim_text: "AI demand keeps growing",
            required_evidence: [],
            verification_status: "pending",
            verification_summary: null,
            thesis_id: thesisId,
            evidence_doc_ids: [],
          }),
          { status: 200 },
        );
      }
      if (u.includes("/investment/claims")) {
        return new Response(
          JSON.stringify([
            {
              id: "cl_1",
              workspace_id: "ws_default",
              claim_text: "AI demand keeps growing",
              required_evidence: [],
              verification_status: "pending",
              verification_summary: null,
              thesis_id: thesisId,
              evidence_doc_ids: [],
            },
          ]),
          { status: 200 },
        );
      }
      if (u.includes("/investment/theses")) {
        return new Response(
          JSON.stringify([
            {
              id: "th_1",
              workspace_id: "ws_default",
              title: "AI capex remains strong",
              status: "open",
              confidence: "medium",
            },
          ]),
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

    expect(await screen.findByText("AI demand keeps growing")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "关联假设" }));
    fireEvent.click(await screen.findByText("AI capex remains strong"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/investment/claims/cl_1/status"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            verification_status: "pending",
            thesis_id: "th_1",
          }),
        }),
      );
    });
  });

  it("renders clickable evidence URLs and an explicit missing-link state", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/investment/claims")) {
        return new Response(
          JSON.stringify([
            {
              id: "cl_evidence",
              workspace_id: "ws_default",
              claim_text: "Evidence links are reviewable",
              required_evidence: [],
              verification_status: "verified",
              verification_summary: null,
              source_item_id: "item_evidence",
              evidence_doc_ids: ["item_evidence", "missing_doc", "https://example.com/direct"],
            },
          ]),
          { status: 200 },
        );
      }
      if (u.includes("/investment/items")) {
        return new Response(
          JSON.stringify([
            {
              id: "item_evidence",
              workspace_id: "ws_default",
              title: "Evidence item",
              source_url: "https://x.com/analyst/status/42",
            },
          ]),
          { status: 200 },
        );
      }
      if (u.includes("/investment/watchlist")) return new Response(JSON.stringify([]), { status: 200 });
      if (u.includes("/investment/theses")) return new Response(JSON.stringify([]), { status: 200 });
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("Evidence links are reviewable")).toBeInTheDocument();
    const itemLink = screen.getByRole("link", { name: /item_evidence/ });
    expect(itemLink).toHaveAttribute("href", "https://x.com/analyst/status/42");
    expect(itemLink).toHaveAttribute("target", "_blank");
    const directLink = screen.getByRole("link", { name: /example\.com\/direct/ });
    expect(directLink).toHaveAttribute("href", "https://example.com/direct");
    expect(screen.getByText(/原文链接缺失：missing_doc/)).toBeInTheDocument();
  });
});
