import { Empty, Space, Tag, Timeline, Typography } from "antd";
import type { DigestOutcome } from "../../services/investmentApi";

type OutcomeTimelineProps = {
  outcomes: DigestOutcome[];
};

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("zh-CN");
}

function windowValue(outcome: DigestOutcome, window: "1d" | "3d" | "5d"): string {
  const value = outcome[`realized_${window}`];
  return typeof value === "number" ? `${(value * 100).toFixed(2)}%` : "—";
}

/** Compact, append-only outcome history for a digest or opportunity detail. */
export function OutcomeTimeline({ outcomes }: OutcomeTimelineProps) {
  if (outcomes.length === 0) return <Empty description="暂无结果复盘" />;

  return (
    <Timeline
      items={outcomes.map((outcome) => ({
        key: outcome.id,
        color: outcome.outcome_status === "invalidated" ? "red" : "green",
        children: (
          <Space direction="vertical" size={4}>
            <Space wrap>
              <Typography.Text strong>
                {outcome.opportunity_title ?? outcome.recommendation_id ?? "推荐结果"}
              </Typography.Text>
              <Tag>{formatDate(outcome.observed_at)}</Tag>
              <Tag color={outcome.adopted ? "blue" : "default"}>
                {outcome.adopted ? "已采用" : "未采用"}
              </Tag>
              {outcome.catalyst_result && <Tag>{outcome.catalyst_result}</Tag>}
            </Space>
            <Typography.Text type="secondary">
              1D {windowValue(outcome, "1d")} · 3D {windowValue(outcome, "3d")} · 5D{" "}
              {windowValue(outcome, "5d")}
            </Typography.Text>
            {(outcome.failure_reason ?? outcome.outcome_note) && (
              <Typography.Text type="danger">
                失败原因：{outcome.failure_reason ?? outcome.outcome_note}
              </Typography.Text>
            )}
          </Space>
        ),
      }))}
    />
  );
}

