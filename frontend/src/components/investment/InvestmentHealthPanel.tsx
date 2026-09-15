import { Card, Empty, List, Space, Tag, Typography } from "antd";

import type { InvestmentHealth, InvestmentHealthState } from "../../services/investmentApi";

const STATE_LABELS: Record<InvestmentHealthState, string> = {
  healthy: "数据正常",
  delayed: "数据延迟",
  stale: "数据已过期",
  failed: "抓取失败",
};

const STATE_COLORS: Record<InvestmentHealthState, string> = {
  healthy: "success",
  delayed: "warning",
  stale: "error",
  failed: "error",
};

function formatTime(value?: string | null): string {
  if (!value) return "暂无记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "暂无记录";
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function ageLabel(hours?: number | null): string {
  if (hours === undefined || hours === null) return "暂无数据时间";
  if (hours < 1) return "不到 1 小时前";
  if (hours < 24) return `${Math.round(hours)} 小时前`;
  return `${Math.round(hours / 24)} 天前`;
}

export function InvestmentHealthPanel({ health }: { health: InvestmentHealth | null }) {
  if (!health) return null;
  const sources = Array.isArray(health.sources) ? health.sources : [];
  return (
    <Card
      size="small"
      title="数据新鲜度"
      extra={<Tag color={STATE_COLORS[health.freshness_state]}>{STATE_LABELS[health.freshness_state]}</Tag>}
      className="investment-health-panel"
      style={{ marginBottom: 16 }}
    >
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <Typography.Text type="secondary">
          最新情报：{ageLabel(health.newest_item_age_hours)}
          {health.newest_item_at ? `（${formatTime(health.newest_item_at)}）` : ""}
        </Typography.Text>
        {sources.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无已配置数据源" />
        ) : (
          <List
            size="small"
            dataSource={sources}
            renderItem={(source) => (
              <List.Item>
                <List.Item.Meta
                  title={
                    <Space wrap>
                      <Typography.Text strong>{source.name}</Typography.Text>
                      <Tag color={STATE_COLORS[source.health_state]}>{STATE_LABELS[source.health_state]}</Tag>
                    </Space>
                  }
                  description={
                    <Space wrap size={[8, 2]}>
                      <span>最新内容：{ageLabel(source.newest_item_age_hours)}</span>
                      <span>最近成功：{formatTime(source.last_success_at)}</span>
                      {source.consecutive_failures > 0 && <span>连续失败 {source.consecutive_failures} 次</span>}
                      {source.last_error && <Typography.Text type="danger">{source.last_error}</Typography.Text>}
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Space>
    </Card>
  );
}
