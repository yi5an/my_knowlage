import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Tabs,
  Typography,
  message,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type InvestmentFact,
  type InvestmentItem,
  type InvestmentSignal,
  type InvestmentSource,
  type InvestmentThesis,
  type InvestmentWatchlist,
} from "../services/investmentApi";

export function InvestmentWatchlistPage() {
  const [items, setItems] = useState<InvestmentWatchlist[]>([]);
  const [sources, setSources] = useState<InvestmentSource[]>([]);
  const [selectedWatchlistId, setSelectedWatchlistId] = useState<string | null>(null);
  const [detailSources, setDetailSources] = useState<InvestmentSource[]>([]);
  const [detailItems, setDetailItems] = useState<InvestmentItem[]>([]);
  const [detailSignals, setDetailSignals] = useState<InvestmentSignal[]>([]);
  const [detailFacts, setDetailFacts] = useState<InvestmentFact[]>([]);
  const [detailTheses, setDetailTheses] = useState<InvestmentThesis[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [bindSourceOpen, setBindSourceOpen] = useState(false);
  const [bindingSources, setBindingSources] = useState(false);
  const [pollingSourceIds, setPollingSourceIds] = useState<Record<string, boolean>>({});
  const [form] = Form.useForm();
  const [bindSourceForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextWatchlist, nextSources] = await Promise.all([
        investmentApi.listWatchlist(),
        investmentApi.listSources(),
      ]);
      setItems(nextWatchlist);
      setSources(nextSources);
      setSelectedWatchlistId((current) => {
        if (current && nextWatchlist.some((watchlist) => watchlist.id === current)) {
          return current;
        }
        return nextWatchlist[0]?.id ?? null;
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedWatchlistId) {
      setDetailSources([]);
      setDetailItems([]);
      setDetailSignals([]);
      setDetailFacts([]);
      setDetailTheses([]);
      return;
    }
    let alive = true;
    setDetailLoading(true);
    setDetailError(null);
    Promise.all([
      investmentApi.listWatchlistSources(selectedWatchlistId),
      investmentApi.listItems({ watchlistId: selectedWatchlistId, limit: 10 }),
      investmentApi.listSignals({ watchlistId: selectedWatchlistId, status: "tracking", limit: 10 }),
      investmentApi.listFacts({
        watchlistId: selectedWatchlistId,
        verificationStatus: "pending",
        limit: 10,
      }),
      investmentApi.listTheses("ws_default", selectedWatchlistId),
    ])
      .then(([nextSources, nextItems, nextSignals, nextFacts, nextTheses]) => {
        if (!alive) return;
        setDetailSources(nextSources);
        setDetailItems(nextItems);
        setDetailSignals(nextSignals);
        setDetailFacts(nextFacts);
        setDetailTheses(nextTheses);
      })
      .catch((e) => {
        if (!alive) return;
        setDetailError(e instanceof ApiError ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setDetailLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [selectedWatchlistId]);

  const handleCreate = async () => {
    const values = await form.validateFields();
    await investmentApi.createWatchlist({
      name: values.name,
      watch_type: values.watch_type ?? "stock",
      ticker: values.ticker,
      exchange: values.exchange,
      importance: values.importance ?? "medium",
      notes: values.notes,
      keywords: values.keywords ? String(values.keywords).split(",").map((s) => s.trim()) : [],
    });
    setOpen(false);
    form.resetFields();
    void load();
  };

  const handleUnbindSource = async (watchlistId: string, sourceId: string) => {
    try {
      await investmentApi.unbindWatchlistSource(watchlistId, sourceId);
      message.success("已解绑数据源");
      void load();
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : String(e));
    }
  };

  const refreshDetailSources = async () => {
    if (!selectedWatchlistId) return;
    try {
      setDetailSources(await investmentApi.listWatchlistSources(selectedWatchlistId));
      void load();
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : String(e));
    }
  };

  const handleBindSources = async () => {
    if (!selectedWatchlistId) return;
    const values = await bindSourceForm.validateFields();
    const sourceIds = (values.source_ids ?? []) as string[];
    setBindingSources(true);
    try {
      const results = await Promise.allSettled(
        sourceIds.map((sourceId) => investmentApi.bindWatchlistSource(selectedWatchlistId, sourceId)),
      );
      const succeeded = results.filter((result) => result.status === "fulfilled").length;
      const failed = results.find((result) => result.status === "rejected");
      if (succeeded > 0) message.success(`已绑定 ${succeeded} 个信息源`);
      if (failed?.status === "rejected") message.error(String(failed.reason));
      setBindSourceOpen(false);
      bindSourceForm.resetFields();
      await refreshDetailSources();
    } finally {
      setBindingSources(false);
    }
  };

  const handlePollSource = async (source: InvestmentSource) => {
    setPollingSourceIds((current) => ({ ...current, [source.id]: true }));
    try {
      await investmentApi.pollSource(source.id);
      message.success(`${source.name} 已加入抓取队列`);
      await refreshDetailSources();
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setPollingSourceIds((current) => ({ ...current, [source.id]: false }));
    }
  };

  const selectedWatchlist =
    items.find((watchlist) => watchlist.id === selectedWatchlistId) ?? null;

  const renderSourceList = () => (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Button onClick={() => setBindSourceOpen(true)}>绑定已有信息源</Button>
      {detailSources.length === 0 ? (
        <Empty description="暂无绑定信息源" />
      ) : (
        <List
          dataSource={detailSources}
          renderItem={(source) => (
            <List.Item
              actions={[
                <Button key="poll" size="small" loading={!!pollingSourceIds[source.id]} onClick={() => void handlePollSource(source)}>
                  立即抓取
                </Button>,
                <Button key="unbind" size="small" danger onClick={() => void handleUnbindSource(selectedWatchlistId!, source.id)}>
                  解绑
                </Button>,
              ]}
            >
            <List.Item.Meta
              title={
                <Space>
                  <Typography.Text strong>{source.name}</Typography.Text>
                  <Tag>{source.source_type}</Tag>
                  <Tag color={source.enabled ? "green" : "default"}>
                    {source.enabled ? "启用" : "停用"}
                  </Tag>
                </Space>
              }
              description={
                <Space direction="vertical" size={0}>
                  <span>轮询间隔 {source.poll_interval_seconds}s</span>
                  {source.last_error && <Typography.Text type="danger">最近错误：{source.last_error}</Typography.Text>}
                </Space>
              }
            />
            </List.Item>
          )}
        />
      )}
    </Space>
  );

  const renderLatestItems = () =>
    detailItems.length === 0 ? (
      <Empty description="暂无最新信息" />
    ) : (
      <List
        dataSource={detailItems}
        renderItem={(item) => (
          <List.Item>
            <List.Item.Meta
              title={item.title_zh || item.title}
              description={item.summary_zh || item.summary || item.source_url}
            />
            <Space>
              <Tag>{item.info_layer}</Tag>
              <Tag>{item.importance}</Tag>
            </Space>
          </List.Item>
        )}
      />
    );

  const renderSignals = () =>
    detailSignals.length === 0 ? (
      <Empty description="暂无早期信号" />
    ) : (
      <List
        dataSource={detailSignals}
        renderItem={(signal) => {
          const evidenceFacts = signal.fact_ids
            .map((factId) => detailFacts.find((fact) => fact.id === factId))
            .filter((fact): fact is InvestmentFact => Boolean(fact));
          return (
            <List.Item>
              <List.Item.Meta
                title={signal.title}
                description={
                  <Space direction="vertical" size={2}>
                    <span>{signal.summary}</span>
                    <span>
                      首次出现：{signal.first_seen_at.slice(0, 16)}；最近：
                      {signal.last_seen_at.slice(0, 16)}
                    </span>
                    {evidenceFacts.map((fact) => (
                      <Space key={fact.id} size={8} wrap>
                        <span>证据：{fact.evidence_excerpt}</span>
                        {fact.evidence_url && (
                          <a href={fact.evidence_url} target="_blank" rel="noreferrer">
                            打开证据
                          </a>
                        )}
                      </Space>
                    ))}
                  </Space>
                }
              />
              <Space>
                <Tag>来源 {signal.source_count}</Tag>
                <Tag>置信度 {Math.round(signal.confidence * 100)}%</Tag>
              </Space>
            </List.Item>
          );
        }}
      />
    );

  const renderFacts = () =>
    detailFacts.length === 0 ? (
      <Empty description="暂无待验证事实" />
    ) : (
      <List
        dataSource={detailFacts}
        renderItem={(fact) => (
          <List.Item>
            <List.Item.Meta
              title={fact.fact_text_zh || fact.fact_text}
              description={
                <Space direction="vertical" size={0}>
                  <span>证据：{fact.evidence_excerpt}</span>
                  {fact.evidence_url && (
                    <a href={fact.evidence_url} target="_blank" rel="noreferrer">
                      打开证据
                    </a>
                  )}
                </Space>
              }
            />
            <Space>
              <Tag>{fact.fact_type}</Tag>
              <Tag>置信度 {Math.round(fact.confidence * 100)}%</Tag>
            </Space>
          </List.Item>
        )}
      />
    );

  const renderTheses = () =>
    detailTheses.length === 0 ? (
      <Empty description="暂无相关假设" />
    ) : (
      <List
        dataSource={detailTheses}
        renderItem={(thesis) => (
          <List.Item>
            <List.Item.Meta title={thesis.title} description={thesis.body} />
            <Space>
              <Tag>{thesis.status}</Tag>
              <Tag>{thesis.confidence}</Tag>
            </Space>
          </List.Item>
        )}
      />
    );

  return (
    <main className="page">
      <PageHeader
        title="观察对象"
        description="管理你关注的股票 / 公司 / 宏观主题。"
        extra={<Button type="primary" onClick={() => setOpen(true)}>添加观察对象</Button>}
      />
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}
      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "minmax(280px, 360px) 1fr" }}>
        <Card>
          <Spin spinning={loading}>
            {items.length === 0 ? (
              <Empty description="暂无观察对象" />
            ) : (
              <List
                dataSource={items}
                renderItem={(w) => (
                  <List.Item
                    onClick={() => setSelectedWatchlistId(w.id)}
                    style={{
                      cursor: "pointer",
                      background: selectedWatchlistId === w.id ? "#f0f7ff" : undefined,
                      paddingInline: 12,
                    }}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <Typography.Text strong>{w.name}</Typography.Text>
                          {w.ticker && <Tag color="blue">{w.ticker}</Tag>}
                          {w.exchange && <Tag>{w.exchange}</Tag>}
                          <Tag>{w.importance}</Tag>
                        </Space>
                      }
                      description={
                        <Space direction="vertical" size={0}>
                          {w.keywords?.length > 0 && (
                            <span>关键词：{w.keywords.join("、")}</span>
                          )}
                          <Space size={[0, 4]} wrap>
                            <Typography.Text type="secondary">数据源：</Typography.Text>
                            {sources.filter((source) => source.default_watchlist_ids.includes(w.id))
                              .length > 0 ? (
                              sources
                                .filter((source) => source.default_watchlist_ids.includes(w.id))
                                .map((source) => (
                                  <Tag
                                    key={source.id}
                                    closable
                                    onClose={(event) => {
                                      event.preventDefault();
                                      event.stopPropagation();
                                      void handleUnbindSource(w.id, source.id);
                                    }}
                                  >
                                    {source.name}
                                  </Tag>
                                ))
                            ) : (
                              <Typography.Text type="secondary">未绑定</Typography.Text>
                            )}
                          </Space>
                          {w.notes && <span>{w.notes}</span>}
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Spin>
        </Card>

        <Card
          title={selectedWatchlist ? `${selectedWatchlist.name} 详情` : "观察对象详情"}
        >
          {detailError && (
            <Alert type="error" message={detailError} style={{ marginBottom: 16 }} showIcon />
          )}
          <Spin spinning={detailLoading}>
            {!selectedWatchlist ? (
              <Empty description="请选择观察对象" />
            ) : (
              <Tabs
                items={[
                  { key: "sources", label: "信息源", children: renderSourceList() },
                  { key: "items", label: "最新信息", children: renderLatestItems() },
                  { key: "signals", label: "早期信号", children: renderSignals() },
                  { key: "facts", label: "待验证事实", children: renderFacts() },
                  { key: "theses", label: "相关假设", children: renderTheses() },
                ]}
              />
            )}
          </Spin>
        </Card>
      </div>

      <Modal
        open={open}
        title="添加观察对象"
        onCancel={() => setOpen(false)}
        onOk={handleCreate}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item label="名称" name="name" rules={[{ required: true }]}>
            <Input placeholder="如：Apple" />
          </Form.Item>
          <Form.Item label="类型" name="watch_type" initialValue="stock">
            <Select
              options={[
                { value: "stock", label: "股票" },
                { value: "company", label: "公司" },
                { value: "macro", label: "宏观主题" },
                { value: "etf", label: "ETF" },
              ]}
            />
          </Form.Item>
          <Form.Item label="代码" name="ticker">
            <Input placeholder="如：AAPL" />
          </Form.Item>
          <Form.Item label="交易所" name="exchange">
            <Input placeholder="如：NASDAQ" />
          </Form.Item>
          <Form.Item label="重要性" name="importance" initialValue="medium">
            <Select
              options={[
                { value: "low", label: "低" },
                { value: "medium", label: "中" },
                { value: "high", label: "高" },
              ]}
            />
          </Form.Item>
          <Form.Item label="关键词（逗号分隔）" name="keywords">
            <Input placeholder="财报, AI, 数据中心" />
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={bindSourceOpen}
        title="绑定已有信息源"
        onCancel={() => setBindSourceOpen(false)}
        onOk={() => void handleBindSources()}
        confirmLoading={bindingSources}
        okText="绑定"
        cancelText="取消"
      >
        <Form form={bindSourceForm} layout="vertical">
          <Form.Item label="选择已有信息源" name="source_ids" rules={[{ required: true, message: "请选择至少一个信息源" }]}>
            <Select
              mode="multiple"
              options={sources
                .filter((source) => !detailSources.some((bound) => bound.id === source.id))
                .map((source) => ({ value: source.id, label: source.name }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </main>
  );
}
