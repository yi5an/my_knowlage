import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { recommendationFixture } from "../test/fixtures/investmentFixtures";
import { AccountDiscoveryPage } from "./AccountDiscoveryPage";

describe("AccountDiscoveryPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("explains why an account is recommended and follows it idempotently", async () => {
    const responder = recommendationFixture({
      reason: "过去 30 天持续提供可验证的一手线索",
    });
    const fetchMock = vi.fn((url: string, init?: RequestInit) => responder(url, init));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <AccountDiscoveryPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/过去 30 天/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+ 关注追踪" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "已关注" })).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "查看人物影响" })).toHaveAttribute(
      "href",
      "/investment/person-sources/person_fixture/impact",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/investment/account-recommendations/rec_fixture/follow"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("distinguishes built-in seed recommendations from unavailable external search", async () => {
    const responder = recommendationFixture({
      score_breakdown: { seeded: 1, source_quality: 0.9 },
      reason: "KnowPilot 内置关注建议。搜索服务未配置，未扩展外部候选。",
    });
    vi.stubGlobal("fetch", vi.fn(responder));
    render(
      <MemoryRouter>
        <AccountDiscoveryPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("内置种子推荐")).toBeInTheDocument();
    expect(screen.getByText(/外部搜索未配置/)).toBeInTheDocument();
  });
});
