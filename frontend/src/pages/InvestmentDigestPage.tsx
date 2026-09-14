import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  List,
  Row,
  Select,
  Skeleton,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { ImpactTag } from "../components/investment/ImpactTag";
import { InfoLayerTag } from "../components/investment/InfoLayerTag";
import { OpportunityCandidateCard } from "../components/investment/OpportunityCandidateCard";
import { OutcomeTimeline } from "../components/investment/OutcomeTimeline";
import { ReviewStatusTag } from "../components/investment/ReviewStatusTag";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type InvestmentDigest,
  type InvestmentDigestSnapshot,
  type InvestmentWatchlist,
} from "../services/investmentApi";

const EMPTY: InvestmentDigest = {
  counts: {
    pending_review_count: 0,
    pending_claims_count: 0,
    theses_challenged_count: 0,
    today_primary_count: 0,
    today_macro_count: 0,
    untranslated_count: 0,
    unextracted_count: 0,
    unsignaled_count: 0,
    failed_job_count: 0,
  },
  today_highlights: [],
  pending_claims: [],
  challenged_items: [],
  early_signals: [],
  pending_facts: [],
  opportunities: [],
  person_impact_events: [],
  outcomes: [],
};

export function InvestmentDigestPage() {
  const [digest, setDigest] = useState<InvestmentDigest>(EMPTY);
  const [snapshots, setSnapshots] = useState<InvestmentDigestSnapshot[]>([]);
  const [watchlist, setWatchlist] = useState<InvestmentWatchlist[]>([]);
  const [watchlistId, setWatchlistId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextDigest, nextWatchlist, nextSnapshots] = await Promise.all([
        investmentApi.getDigest({ watchlistId }),
        investmentApi.listWatchlist(),
        investmentApi.listDigestSnapshots({ watchlistId, limit: 5 }),
      ]);
      setDigest(nextDigest);
      setWatchlist(nextWatchlist);
      setSnapshots(nextSnapshots);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [watchlistId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSaveSnapshot = async () => {
    setSaving(true);
    try {
      await investmentApi.createDigestSnapshot({ watchlistId });
      message.success("简报快照已保存");
      await load();
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const opportunities = digest.opportunities ?? [];
  const personImpactEvents = digest.person_impact_events ?? [];
  const outcomes = digest.outcomes ?? [];

  return (
    <main className="page">
      <PageHeader
        title="每日简报"
        description="当日投资信息聚合：统计概览 + 今日重点 + 待验证观点 + 假设被挑战。"
        extra={
          <Space>
            <Select
              allowClear
              placeholder="全部观察对象"
              style={{ minWidth: 220 }}
              value={watchlistId}
              onChange={(value) => setWatchlistId(value)}
              options={watchlist.map((w) => ({ value: w.id, label: w.name }))}
            />
            <Button loading={saving} onClick={() => void handleSaveSnapshot()}>
              保存快照
            </Button>
          </Space>
        }
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

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={24}>
            <Card
              title="高优先机会"
              extra={<Typography.Text type="secondary">证据驱动 · 仅作研究假设</Typography.Text>}
            >
              {opportunities.length === 0 ? (
                <Empty description="暂无高优先机会候选" />
              ) : (
                <div className="opportunity-card-grid">
                  {opportunities.slice(0, 5).map((candidate) => (
                    <OpportunityCandidateCard key={candidate.id} candidate={candidate} />
                  ))}
                </div>
              )}
            </Card>
          </Col>
          <Col span={12}>
            <Card title="人物影响事件" style={{ height: "100%" }}>
              {personImpactEvents.length === 0 ? (
                <Empty description="暂无人物影响事件" />
              ) : (
                <List
                  dataSource={personImpactEvents}
                  renderItem={(event) => (
                    <List.Item>
                      <List.Item.Meta
                        title={
                          <Space wrap>
                            <Typography.Text strong>
                              {event.symbol} · {event.event_status}
                            </Typography.Text>
                            <Tag color="blue">置信度 {Math.round(event.confidence * 100)}%</Tag>
                          </Space>
                        }
                        description={
                          <Space direction="vertical" size={2}>
                            <Typography.Text type="secondary">
                              {new Date(event.event_at).toLocaleDateString("zh-CN")} · 基准 {event.benchmark_symbol}
                            </Typography.Text>
                            <Typography.Text>{event.reason ?? "暂无结论"}</Typography.Text>
                            {event.source_url ? (
                              <Typography.Link
                                href={event.source_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                查看原文证据
                              </Typography.Link>
                            ) : (
                              <Typography.Text type="secondary">原文链接缺失</Typography.Text>
                            )}
                          </Space>
                        }
                      />
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </Col>
          <Col span={12}>
            <Card title="结果复盘" style={{ height: "100%" }}>
              <OutcomeTimeline outcomes={outcomes} />
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={12}>
            <Card title="早期信号" style={{ height: "100%" }}>
              {digest.early_signals.length === 0 ? (
                <Empty description="暂无早期信号" />
              ) : (
                <List
                  dataSource={digest.early_signals}
                  renderItem={(signal) => (
                    <List.Item>
                      <List.Item.Meta
                        title={
                          <Space wrap>
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
          </Col>

          <Col span={12}>
            <Card title="待验证事实" style={{ height: "100%" }}>
              {digest.pending_facts.length === 0 ? (
                <Empty description="暂无待验证事实" />
              ) : (
                <List
                  dataSource={digest.pending_facts}
                  renderItem={(fact) => (
                    <List.Item>
                      <List.Item.Meta
                        title={
                          <Space wrap>
                            <Typography.Text>{fact.fact_text_zh ?? fact.fact_text}</Typography.Text>
                            <Tag>{fact.fact_type}</Tag>
                            <Tag color="blue">置信度 {Math.round(fact.confidence * 100)}%</Tag>
                          </Space>
                        }
                        description={
                          <Space direction="vertical" size={4}>
                            <Typography.Text type="secondary">
                              证据：{fact.evidence_excerpt}
                            </Typography.Text>
                            {fact.evidence_url && (
                              <Typography.Link
                                href={fact.evidence_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                打开证据来源
                              </Typography.Link>
                            )}
                          </Space>
                        }
                      />
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </Col>
        </Row>

        <Card title="历史快照" style={{ marginTop: 16 }}>
          {snapshots.length === 0 ? (
            <Empty description="暂无历史快照" />
          ) : (
            <List
              dataSource={snapshots}
              renderItem={(snapshot) => (
                <List.Item>
                  <List.Item.Meta
                    title={<Typography.Text strong>{snapshot.title}</Typography.Text>}
                    description={
                      <Space wrap>
                        <Typography.Text type="secondary">
                          {new Date(snapshot.digest_date).toLocaleString("zh-CN")}
                        </Typography.Text>
                        <Tag>重点 {snapshot.digest.today_highlights?.length ?? 0}</Tag>
                        <Tag>信号 {snapshot.digest.early_signals?.length ?? 0}</Tag>
                        <Tag>事实 {snapshot.digest.pending_facts?.length ?? 0}</Tag>
                        <Tag>机会 {snapshot.digest.opportunities?.length ?? 0}</Tag>
                        <Tag>复盘 {snapshot.digest.outcomes?.length ?? 0}</Tag>
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
