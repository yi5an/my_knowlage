import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  List,
  Row,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { InvestmentItemDrawer } from "../components/investment/InvestmentItemDrawer";
import { InfoLayerTag } from "../components/investment/InfoLayerTag";
import { OpportunityCandidateCard } from "../components/investment/OpportunityCandidateCard";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type InfoLayer,
  type InvestmentDashboard,
  type InvestmentItem,
  type InvestmentSignal,
  type OpportunityCandidate,
} from "../services/investmentApi";
import { PageHeader } from "../components/PageHeader";

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

const LAYER_LABELS: Record<string, string> = {
  all: "全部层级",
  primary_source: "一手信息",
  macro_calendar: "宏观",
  news: "新闻",
  opinion: "观点",
};

const ERROR_LABELS: Record<string, string> = {
  dashboard: "摘要指标",
  items: "最新情报",
  signals: "正在发生",
  opportunities: "机会候选",
};

type Endpoint = keyof typeof ERROR_LABELS;

function formatDate(value: Date): string {
  return value.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function formatTime(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function itemMatchesObject(item: InvestmentItem, objectId: string): boolean {
  if (objectId === "all") return true;
  return item.theme_id === objectId;
}

function isWithin24Hours(item: InvestmentItem): boolean {
  const raw = item.event_at ?? item.published_at ?? item.review_at;
  if (!raw) return false;
  const timestamp = new Date(raw).getTime();
  if (Number.isNaN(timestamp)) return false;
  return Date.now() - timestamp <= 24 * 60 * 60 * 1000;
}

function itemDescription(item: InvestmentItem): string {
  return item.summary_zh ?? item.summary ?? "暂无摘要";
}

export function IntelligenceFlowPage() {
  const [dashboard, setDashboard] = useState<InvestmentDashboard>(EMPTY_DASHBOARD);
  const [items, setItems] = useState<InvestmentItem[]>([]);
  const [signals, setSignals] = useState<InvestmentSignal[]>([]);
  const [opportunities, setOpportunities] = useState<OpportunityCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<Partial<Record<Endpoint, string>>>({});
  const [objectId, setObjectId] = useState("all");
  const [layer, setLayer] = useState<"all" | InfoLayer>("all");
  const [highImpactOnly, setHighImpactOnly] = useState(false);
  const [recentOnly, setRecentOnly] = useState(false);
  const [selectedItem, setSelectedItem] = useState<InvestmentItem | null>(null);
  const [selectedOpportunity, setSelectedOpportunity] = useState<OpportunityCandidate | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErrors({});
    const result = await Promise.allSettled([
      investmentApi.getDashboard(),
      investmentApi.listItems({ limit: 30 }),
      investmentApi.listSignals({ limit: 20 }),
      investmentApi.listOpportunityCandidates({ limit: 20 }),
    ]);
    const nextErrors: Partial<Record<Endpoint, string>> = {};
    const readError = (value: unknown): string =>
      value instanceof ApiError || value instanceof Error ? value.message : String(value);
    const [dashboardResult, itemsResult, signalsResult, opportunitiesResult] = result;

    if (dashboardResult.status === "fulfilled") setDashboard(dashboardResult.value);
    else nextErrors.dashboard = readError(dashboardResult.reason);
    if (itemsResult.status === "fulfilled") setItems(itemsResult.value);
    else nextErrors.items = readError(itemsResult.reason);
    if (signalsResult.status === "fulfilled") setSignals(signalsResult.value);
    else nextErrors.signals = readError(signalsResult.reason);
    if (opportunitiesResult.status === "fulfilled") setOpportunities(opportunitiesResult.value);
    else nextErrors.opportunities = readError(opportunitiesResult.reason);

    setErrors(nextErrors);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const objectOptions = useMemo(() => {
    const ids = new Set<string>();
    items.forEach((item) => {
      if (item.theme_id) ids.add(item.theme_id);
    });
    return [
      { value: "all", label: "全部对象" },
      ...Array.from(ids).map((id) => ({ value: id, label: id })),
    ];
  }, [items]);

  const filteredItems = useMemo(
    () =>
      items.filter((item) => {
        if (!itemMatchesObject(item, objectId)) return false;
        if (layer !== "all" && item.info_layer !== layer) return false;
        if (highImpactOnly && item.importance !== "high") return false;
        if (recentOnly && !isWithin24Hours(item)) return false;
        return true;
      }),
    [highImpactOnly, items, layer, objectId, recentOnly],
  );

  const highPriorityOpportunities = useMemo(
    () =>
      opportunities
        .filter((candidate) =>
          ["high_priority_research", "research"].includes(candidate.priority),
        )
        .slice(0, 5),
    [opportunities],
  );

  const errorKeys = Object.keys(errors) as Endpoint[];

  return (
    <main className="page intelligence-flow-page">
      <PageHeader
        title="情报流"
        description="把最新情报、正在发生的信号和待验证机会放在同一条工作流里。"
        extra={
          <Space direction="vertical" align="end" size={2}>
            <Typography.Text strong>{formatDate(new Date())}</Typography.Text>
            <Typography.Text type="secondary">数据范围：过去 24 小时 · 自动更新</Typography.Text>
          </Space>
        }
      />

      {loading && (
        <Alert
          className="intelligence-flow-status"
          type="info"
          showIcon
          message="正在加载情报流"
        />
      )}
      {errorKeys.length > 0 && (
        <Alert
          className="intelligence-flow-status"
          type="warning"
          showIcon
          message="部分数据加载失败"
          description={
            <Space direction="vertical" size={4}>
              <Typography.Text>
                {errorKeys.map((key) => `${ERROR_LABELS[key]}：${errors[key]}`).join("；")}
              </Typography.Text>
              <Button aria-label="重试" icon={<ReloadOutlined />} size="small" onClick={() => void load()}>
                重试
              </Button>
            </Space>
          }
        />
      )}

      <Row gutter={[12, 12]} className="intelligence-flow-metrics">
        <Col xs={12} md={6}>
          <Card><Statistic title="值得注意" value={dashboard.pending_review_count} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="机会线索" value={opportunities.length} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="假设受挑战" value={dashboard.theses_challenged_count} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="待验证" value={dashboard.pending_claims_count} /></Card>
        </Col>
      </Row>

      <Card className="intelligence-flow-filters" size="small">
        <Space wrap size={[12, 8]}>
          <Select
            aria-label="对象筛选"
            value={objectId}
            options={objectOptions}
            onChange={setObjectId}
            style={{ minWidth: 150 }}
          />
          <Select
            aria-label="来源层筛选"
            value={layer}
            options={Object.entries(LAYER_LABELS).map(([value, label]) => ({ value, label }))}
            onChange={(value: "all" | InfoLayer) => setLayer(value)}
            style={{ minWidth: 130 }}
          />
          <Checkbox checked={highImpactOnly} onChange={(event) => setHighImpactOnly(event.target.checked)}>
            高影响
          </Checkbox>
          <Checkbox checked={recentOnly} onChange={(event) => setRecentOnly(event.target.checked)}>
            24 小时
          </Checkbox>
          <Tag color="default">筛选后 {filteredItems.length} 条情报</Tag>
        </Space>
      </Card>

      <section className="intelligence-flow-section">
        <div className="intelligence-flow-section__header">
          <div>
            <Typography.Title level={4}>高优先研究</Typography.Title>
            <Typography.Text type="secondary">从信号中筛出的机会候选，只作为待验证假设。</Typography.Text>
          </div>
          <Link to="/investment">查看全部机会候选</Link>
        </div>
        {highPriorityOpportunities.length === 0 ? (
          <Card><Empty description="暂无高优先机会候选" /></Card>
        ) : (
          <div className="opportunity-card-grid">
            {highPriorityOpportunities.map((candidate) => (
              <OpportunityCandidateCard
                key={candidate.id}
                candidate={candidate}
                onOpen={setSelectedOpportunity}
              />
            ))}
          </div>
        )}
      </section>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <section className="intelligence-flow-section">
            <div className="intelligence-flow-section__header">
              <div>
                <Typography.Title level={4}>最新情报</Typography.Title>
                <Typography.Text type="secondary">按来源层和影响筛选，点击可查看证据。</Typography.Text>
              </div>
              <Link to="/investment/items">查看全部</Link>
            </div>
            <Card>
              {filteredItems.length === 0 ? (
                <Empty description={items.length === 0 ? "暂无最新情报" : "没有匹配的情报"} />
              ) : (
                <List
                  dataSource={filteredItems.slice(0, 10)}
                  renderItem={(item) => (
                    <List.Item
                      className="intelligence-flow-item"
                      onClick={() => setSelectedItem(item)}
                    >
                      <List.Item.Meta
                        title={
                          <Space wrap>
                            <InfoLayerTag layer={item.info_layer} />
                            <Typography.Text strong>{item.title_zh ?? item.title}</Typography.Text>
                            {item.importance === "high" && <Tag color="red">高影响</Tag>}
                          </Space>
                        }
                        description={
                          <Space direction="vertical" size={2}>
                            <Typography.Text type="secondary" ellipsis>
                              {itemDescription(item)}
                            </Typography.Text>
                            <Typography.Text type="secondary">
                              {item.source_name ?? "未知来源"}
                              {formatTime(item.event_at ?? item.published_at)
                                ? ` · ${formatTime(item.event_at ?? item.published_at)}`
                                : ""}
                            </Typography.Text>
                          </Space>
                        }
                      />
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </section>
        </Col>
        <Col xs={24} lg={10}>
          <section className="intelligence-flow-section">
            <div className="intelligence-flow-section__header">
              <div>
                <Typography.Title level={4}>正在发生</Typography.Title>
                <Typography.Text type="secondary">多个来源共同出现、值得继续跟踪的信号。</Typography.Text>
              </div>
              <Link to="/investment/edge">查看信号</Link>
            </div>
            <Card>
              {signals.length === 0 ? (
                <Empty description="暂无正在发生的信号" />
              ) : (
                <List
                  dataSource={signals.slice(0, 8)}
                  renderItem={(signal) => (
                    <List.Item>
                      <List.Item.Meta
                        title={
                          <Space wrap>
                            <Typography.Text strong>{signal.title}</Typography.Text>
                            <Tag color="blue">来源 {signal.source_count}</Tag>
                          </Space>
                        }
                        description={
                          <Space direction="vertical" size={2}>
                            <Typography.Text>{signal.summary}</Typography.Text>
                            <Typography.Text type="secondary">
                              置信度 {Math.round(signal.confidence * 100)}%
                              {formatTime(signal.last_seen_at) ? ` · 最近 ${formatTime(signal.last_seen_at)}` : ""}
                            </Typography.Text>
                          </Space>
                        }
                      />
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </section>
        </Col>
      </Row>

      <InvestmentItemDrawer
        item={selectedItem}
        opportunity={selectedOpportunity}
        open={selectedItem !== null || selectedOpportunity !== null}
        onClose={() => {
          setSelectedItem(null);
          setSelectedOpportunity(null);
        }}
        onUpdated={() => void load()}
      />
    </main>
  );
}
