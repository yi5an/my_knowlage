import { Card, Progress, Space, Tag, Typography } from "antd";
import type { InvestmentSignal } from "../../services/investmentApi";
import { SourceLayerTag } from "./SourceLayerTag";

function actionColor(actionability?: string): string {
  if (actionability === "immediate_attention") return "red";
  if (actionability === "watch") return "gold";
  if (actionability === "noise") return "default";
  return "blue";
}

function actionLabel(actionability?: string): string {
  if (actionability === "immediate_attention") return "立即关注";
  if (actionability === "watch") return "持续观察";
  if (actionability === "noise") return "噪音";
  return "弱信号";
}

export function InformationEdgeCard({ signal }: { signal: InvestmentSignal }) {
  const score = Math.round((signal.information_edge_score ?? 0) * 100);
  return (
    <Card size="small">
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <Space wrap>
          <Typography.Text strong>{signal.title}</Typography.Text>
          <Tag color={actionColor(signal.actionability)}>{actionLabel(signal.actionability)}</Tag>
          <Tag>{signal.signal_stage ?? "new"}</Tag>
          <Tag color="green">置信度 {Math.round(signal.confidence * 100)}%</Tag>
        </Space>
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          {signal.summary}
        </Typography.Paragraph>
        <Space wrap>
          {(signal.source_layers ?? []).map((layer) => (
            <SourceLayerTag key={layer} layer={layer} />
          ))}
          {signal.lead_time_hours != null && (
            <Tag color="purple">领先 {signal.lead_time_hours} 小时</Tag>
          )}
          <Tag color="blue">来源 {signal.source_count}</Tag>
        </Space>
        <Progress percent={score} size="small" status={score >= 75 ? "exception" : "active"} />
      </Space>
    </Card>
  );
}
