import {
  Alert,
  Card,
  Col,
  Empty,
  List,
  Row,
  Skeleton,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { ImpactTag } from "../components/investment/ImpactTag";
import { InfoLayerTag } from "../components/investment/InfoLayerTag";
import { ReviewStatusTag } from "../components/investment/ReviewStatusTag";
import { ApiError } from "../services/client";
import { investmentApi, type InvestmentDigest } from "../services/investmentApi";

const EMPTY: InvestmentDigest = {
  counts: {
    pending_review_count: 0,
    pending_claims_count: 0,
    theses_challenged_count: 0,
    today_primary_count: 0,
    today_macro_count: 0,
  },
  today_highlights: [],
  pending_claims: [],
  challenged_items: [],
};

export function InvestmentDigestPage() {
  const [digest, setDigest] = useState<InvestmentDigest>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDigest(await investmentApi.getDigest());
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
        title="每日简报"
        description="当日投资信息聚合：统计概览 + 今日重点 + 待验证观点 + 假设被挑战。"
      />
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}

      <Skeleton loading={loading} active>
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card>
              <Statistic title="今日待处理" value={digest.counts.pending_review_count} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="今日一手信息" value={digest.counts.today_primary_count} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="今日宏观" value={digest.counts.today_macro_count} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="假设被挑战"
                value={digest.counts.theses_challenged_count}
                valueStyle={{
                  color: digest.counts.theses_challenged_count > 0 ? "#cf1322" : undefined,
                }}
              />
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]}>
          <Col span={12}>
            <Card title="今日重点" style={{ height: "100%" }}>
              {digest.today_highlights.length === 0 ? (
                <Empty description="今日暂无重点信息" />
              ) : (
                <List
                  dataSource={digest.today_highlights}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta
                        title={
                          <Space wrap>
                            <InfoLayerTag layer={item.info_layer} />
                            <span>{item.title_zh ?? item.title}</span>
                          </Space>
                        }
                        description={
                          <Space size="large">
                            <Tag color={item.importance === "high" ? "red" : "default"}>
                              {item.importance}
                            </Tag>
                            <ImpactTag direction={item.impact_direction} />
                            <ReviewStatusTag status={item.action_status} />
                            {item.source_name && <span>{item.source_name}</span>}
                          </Space>
                        }
                      />
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </Col>

          <Col span={6}>
            <Card title="待验证观点" style={{ height: "100%" }}>
              {digest.pending_claims.length === 0 ? (
                <Empty description="暂无待验证观点" />
              ) : (
                <List
                  dataSource={digest.pending_claims}
                  renderItem={(claim) => (
                    <List.Item>
                      <List.Item.Meta
                        title={<Typography.Text>{claim.claim_text}</Typography.Text>}
                        description={
                          <Tag color="warning">{claim.verification_status}</Tag>
                        }
                      />
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </Col>

          <Col span={6}>
            <Card title="假设被挑战" style={{ height: "100%" }}>
              {digest.challenged_items.length === 0 ? (
                <Empty description="暂无被挑战的假设" />
              ) : (
                <List
                  dataSource={digest.challenged_items}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta
                        title={
                          <Space wrap>
                            <ImpactTag direction={item.impact_direction} />
                            <span>{item.title_zh ?? item.title}</span>
                          </Space>
                        }
                        description={
                          <Tag color="error">{item.thesis_impact}</Tag>
                        }
                      />
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </Col>
        </Row>
      </Skeleton>
    </main>
  );
}
