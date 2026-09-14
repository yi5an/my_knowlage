import { ArrowRightOutlined, LinkOutlined } from "@ant-design/icons";
import { Button, Card, Descriptions, Space, Tag, Typography } from "antd";
import type { OpportunityCandidate } from "../../services/investmentApi";

const STATUS_LABEL: Record<string, string> = {
  new: "新线索",
  researching: "研究中",
  waiting_for_evidence: "等待证据",
  validated: "已验证",
  invalidated: "已失效",
  parked: "已搁置",
};

type OpportunityCandidateCardProps = {
  candidate: OpportunityCandidate;
  onOpen?: (candidate: OpportunityCandidate) => void;
};

function EvidenceRef({ reference }: { reference: string }) {
  if (/^https?:\/\//i.test(reference)) {
    return (
      <Typography.Link href={reference} target="_blank" rel="noreferrer">
        <LinkOutlined /> {reference}
      </Typography.Link>
    );
  }
  return (
    <Typography.Link href={`/investment/items?item_id=${encodeURIComponent(reference)}`}>
      <LinkOutlined /> {reference}
    </Typography.Link>
  );
}

/**
 * A compact, evidence-first opportunity card. It intentionally has no trade
 * execution controls: a candidate is a hypothesis to validate, not a signal
 * to buy or sell.
 */
export function OpportunityCandidateCard({ candidate, onOpen }: OpportunityCandidateCardProps) {
  const riskText = candidate.risk_flags.length > 0 ? candidate.risk_flags.join("；") : "暂无已知风险";
  const invalidationText =
    candidate.invalidation_conditions.length > 0
      ? candidate.invalidation_conditions.join("；")
      : "尚未定义失效条件";

  return (
    <Card
      className="opportunity-card"
      data-testid="opportunity-card"
      title={
        <Space size={8} wrap>
          <Typography.Text strong>{candidate.title}</Typography.Text>
          <Tag color="gold">{candidate.priority === "high_priority_research" ? "高优先" : candidate.priority}</Tag>
          <Tag color={candidate.status === "validated" ? "green" : "blue"}>
            {STATUS_LABEL[candidate.status] ?? candidate.status}
          </Tag>
        </Space>
      }
      extra={
        onOpen ? (
          <Button type="link" size="small" onClick={() => onOpen(candidate)}>
            查看证据 <ArrowRightOutlined />
          </Button>
        ) : null
      }
    >
      <Descriptions
        className="opportunity-card__details"
        column={1}
        size="small"
        colon={false}
        items={[
          { key: "why-now", label: "为什么现在", children: candidate.change_summary || candidate.impact_path },
          { key: "expected-gap", label: "预期差", children: candidate.expected_case },
          { key: "catalyst", label: "催化剂", children: candidate.catalyst },
          { key: "risk", label: "风险", children: riskText },
          { key: "invalidation", label: "失效条件", children: invalidationText },
          { key: "next-action", label: "下一步", children: candidate.next_action },
        ]}
      />
      <Space className="opportunity-card__evidence" size={[6, 6]} wrap>
        <Typography.Text type="secondary">证据：</Typography.Text>
        {candidate.evidence_refs.length > 0 ? (
          candidate.evidence_refs.map((reference) => (
            <EvidenceRef key={reference} reference={reference} />
          ))
        ) : (
          <Typography.Text type="secondary">暂无证据引用</Typography.Text>
        )}
      </Space>
      <Space className="opportunity-card__meta" size="middle" wrap>
        <Typography.Text type="secondary">
          置信度 {Math.round(candidate.confidence * 100)}%
        </Typography.Text>
        <Typography.Text type="secondary">
          市场反应：{candidate.market_reaction_state || "未知"}
        </Typography.Text>
        {candidate.asset_symbols.length > 0 && (
          <Tag color="cyan">{candidate.asset_symbols.join(" · ")}</Tag>
        )}
      </Space>
    </Card>
  );
}
