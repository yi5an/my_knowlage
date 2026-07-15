import { Button, Card, Col, Empty, List, Row, Skeleton, Space, Statistic, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type InvestmentDashboard,
  type InvestmentItem,
  type InvestmentSignal,
} from "../services/investmentApi";
import { InfoLayerTag } from "../components/investment/InfoLayerTag";
import { ReviewStatusTag } from "../components/investment/ReviewStatusTag";

const EMPTY_DASHBOARD: InvestmentDashboard = {
  pending_review_count: 0,
  pending_claims_count: 0,
  theses_challenged_count: 0,
  today_primary_count: 0,
  today_macro_count: 0,
  untranslated_count: 0,
  unextracted_count: 0,
  unsignaled_count: 0,
  failed_job_count: 0,
};

export function InvestmentDashboardPage() {
  const [dashboard, setDashboard] = useState<InvestmentDashboard>(EMPTY_DASHBOARD);
  const [pending, setPending] = useState<InvestmentItem[]>([]);
  const [challengedItems, setChallengedItems] = useState<InvestmentItem[]>([]);
  const [signals, setSignals] = useState<InvestmentSignal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, items, digest, nextSignals] = await Promise.all([
        investmentApi.getDashboard(),
        investmentApi.listItems({ actionStatus: "pending_review", limit: 10 }),
        investmentApi.getDigest(),
        investmentApi.listSignals({ limit: 5 }),
      ]);
      setDashboard(d);
      setPending(items);
      setChallengedItems(digest.challenged_items);
      setSignals(nextSignals);
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

        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card>
              <Statistic title="待翻译" value={dashboard.untranslated_count} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="待抽取事实" value={dashboard.unextracted_count} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="待生成信号" value={dashboard.unsignaled_count} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="失败任务"
                value={dashboard.failed_job_count}
                valueStyle={{ color: dashboard.failed_job_count > 0 ? "#cf1322" : undefined }}
              />
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
                        <span>{item.title_zh ?? item.title}</span>
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

        <Card title="假设被挑战" style={{ marginBottom: 16 }}>
          {challengedItems.length === 0 ? (
            <Empty description="暂无被挑战的假设" />
          ) : (
            <List
              dataSource={challengedItems}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space>
                        <span>{item.title_zh ?? item.title}</span>
                        <Tag color={item.thesis_impact === "contradicts" ? "red" : "orange"}>
                          影响：{item.thesis_impact}
                        </Tag>
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
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Card>

        <Card title="早期信号">
          {signals.length === 0 ? (
            <Empty description="暂无早期信号" />
          ) : (
            <List
              dataSource={signals}
              renderItem={(signal) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space>
                        <Typography.Text strong>{signal.title}</Typography.Text>
                        <Tag>{signal.signal_type}</Tag>
                        <Tag color="blue">来源 {signal.source_count}</Tag>
                        <Tag color="green">
                          置信度 {Math.round(signal.confidence * 100)}%
                        </Tag>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={4}>
                        <Typography.Text>{signal.summary}</Typography.Text>
                        <Typography.Text type="secondary">
                          关联事实 {signal.fact_ids.length} 条 · 关联信息{" "}
                          {signal.item_ids.length} 条
                        </Typography.Text>
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
