import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OpportunityCandidate } from "../../services/investmentApi";
import { InvestmentItemDrawer } from "./InvestmentItemDrawer";

const opportunity: OpportunityCandidate = {
  id: "opp_excerpt",
  workspace_id: "ws_default",
  title: "AI supply chain inflection",
  asset_symbols: ["NVDA"],
  opportunity_type: "catalyst",
  change_summary: "供应链数据确认新一轮加速，来源摘录必须可回读。",
  expected_case: "盈利预期上修",
  market_case: "市场尚未充分定价",
  impact_path: "供应链 → 出货 → 收入",
  catalyst: "下次业绩更新",
  risk_flags: ["需求回落"],
  invalidation_conditions: ["出货数据反转"],
  next_action: "补充独立来源",
  evidence_refs: ["item_excerpt"],
  confidence: 0.8,
  status: "new",
  priority: "high_priority_research",
  market_reaction_state: "尚未充分反应",
  score_breakdown: {},
  outcome: {},
};

describe("InvestmentItemDrawer opportunity details", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the source excerpt text alongside evidence references", () => {
    render(
      <MemoryRouter>
        <InvestmentItemDrawer
          item={null}
          opportunity={opportunity}
          open
          onClose={() => undefined}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("来源摘录")).toBeInTheDocument();
    expect(screen.getByText(opportunity.change_summary)).toBeInTheDocument();
    expect(screen.getByText(`影响路径：${opportunity.impact_path}`)).toBeInTheDocument();
  });
});
