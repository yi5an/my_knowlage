import { Button, Card, Col, Empty, List, Row, Skeleton, Space, Statistic, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type InvestmentDashboard,
  type InvestmentItem,
} from "../services/investmentApi";
import { InfoLayerTag } from "../components/investment/InfoLayerTag";
import { ReviewStatusTag } from "../components/investment/ReviewStatusTag";

const EMPTY_DASHBOARD: InvestmentDashboard = {
  pending_review_count: 0,
  pending_claims_count: 0,
  theses_challenged_count: 0,
  today_primary_count: 0,
  today_macro_count: 0,
};

export function InvestmentDashboardPage() {
  const [dashboard, setDashboard] = useState<InvestmentDashboard>(EMPTY_DASHBOARD);
  const [pending, setPending] = useState<InvestmentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, items] = await Promise.all([
        investmentApi.getDashboard(),
        investmentApi.listItems({ actionStatus: "pending_review", limit: 10 }),
      ]);
      setDashboard(d);
      setPending(items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="page">
      <PageHeader
        title="投资工作台"
        description="集中追踪一手信息、宏观事件与待验证观点。所有数据来自真实数据源，无示例数据。"
        extra={
          <Space>
            <Link to="/investment/items">
              <Button>信息列表</Button>
            </Link>
            <Link to="/investment/watchlist">
              <Button>观察对象</Button>
            </Link>
            <Link to="/investment/sources">
              <Button type="primary">数据源</Button>
            </Link>
          </Space>
        }
      />

      {error && (
        <Card style={{ marginBottom: 16 }}>
          <Typography.Text type="danger">{error}</Typography.Text>
        </Card>
      )}

      <Skeleton loading={loading} active>
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Card>
              <Statistic title="今日待处理" value={dashboard.pending_review_count} />
            </Card>
          </Col>
          <Col span={5}>
            <Card>
              <Statistic title="待验证观点" value={dashboard.pending_claims_count} />
            </Card>
          </Col>
          <Col span={5}>
            <Card>
              <Statistic
                title="假设被挑战"
                value={dashboard.theses_challenged_count}
                valueStyle={{ color: dashboard.theses_challenged_count > 0 ? "#cf1322" : undefined }}
              />
            </Card>
          </Col>
          <Col span={5}>
            <Card>
              <Statistic title="今日一手信息" value={dashboard.today_primary_count} />
            </Card>
          </Col>
          <Col span={5}>
            <Card>
              <Statistic title="今日宏观事件" value={dashboard.today_macro_count} />
            </Card>
          </Col>
        </Row>

        <Card title="今日待处理信息" style={{ marginBottom: 16 }}>
          {pending.length === 0 ? (
            <Empty description="暂无待处理信息" />
          ) : (
            <List
              dataSource={pending}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space>
                        <InfoLayerTag layer={item.info_layer} />
                        <span>{item.title}</span>
                      </Space>
                    }
                    description={
                      <Space size="large">
                        <span>{item.source_name ?? "未知来源"}</span>
                        {item.source_url && (
                          <Tag>
                            <a href={item.source_url} target="_blank" rel="noreferrer">
                              原文
                            </a>
                          </Tag>
                        )}
                        <ReviewStatusTag status={item.action_status} />
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Card>
      </Skeleton>
    </main>
  );
}
