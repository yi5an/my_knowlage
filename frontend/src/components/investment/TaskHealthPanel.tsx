import { Button, Card, Empty, List, Space, Statistic, Tag, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

import type { InvestmentTaskHealth } from "../../services/investmentApi";

export function TaskHealthPanel({
  health,
  retryingJobId,
  onRetry,
}: {
  health: InvestmentTaskHealth | null;
  retryingJobId?: string | null;
  onRetry: (jobId: string) => void;
}) {
  if (!health) return null;
  return (
    <Card title="任务健康" style={{ marginBottom: 16 }}>
      <Space wrap size={[16, 12]} style={{ marginBottom: 16 }}>
        <Statistic title="待处理" value={health.pending_count} />
        <Statistic title="运行中" value={health.running_count} />
        <Statistic title="已完成" value={health.succeeded_count} />
        <Statistic title="失败" value={health.failed_count} valueStyle={{ color: health.failed_count > 0 ? "#cf1322" : undefined }} />
      </Space>
      {health.recent_failures.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无失败任务" />
      ) : (
        <List
          size="small"
          header={<Typography.Text strong>最近失败任务</Typography.Text>}
          dataSource={health.recent_failures}
          renderItem={(failure) => (
            <List.Item
              actions={[
                failure.retryable ? (
                  <Button
                    key="retry"
                    size="small"
                    aria-label="重试"
                    icon={<ReloadOutlined />}
                    loading={retryingJobId === failure.job_id}
                    onClick={() => onRetry(failure.job_id)}
                  >
                    重试
                  </Button>
                ) : (
                  <Tag key="not-retryable">不可重试</Tag>
                ),
              ]}
            >
              <List.Item.Meta
                title={<Space><Typography.Text>{failure.job_type}</Typography.Text><Tag color="error">失败</Tag></Space>}
                description={failure.error_message ?? "未提供错误详情"}
              />
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}
