import {
  Alert,
  Button,
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
import { Link } from "react-router-dom";

import { InfoLayerTag } from "../components/investment/InfoLayerTag";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type InformationEdgeDigest,
  type InvestmentItem,
  type InvestmentSource,
  type InvestmentTheme,
  type ThemeSourceBinding,
} from "../services/investmentApi";

const EMPTY_EDGE: InformationEdgeDigest = {
  generated_at: "",
  top_signals: [],
  source_traces: [],
  unvalidated_signals: [],
  stale_or_noise: [],
};

export function InvestmentThemesPage() {
  const [themes, setThemes] = useState<InvestmentTheme[]>([]);
  const [selectedThemeId, setSelectedThemeId] = useState<string | null>(null);
  const [sources, setSources] = useState<InvestmentSource[]>([]);
  const [themeSources, setThemeSources] = useState<ThemeSourceBinding[]>([]);
  const [themeItems, setThemeItems] = useState<InvestmentItem[]>([]);
  const [themeEdge, setThemeEdge] = useState<InformationEdgeDigest>(EMPTY_EDGE);
  const [loading, setLoading] = useState(false);
  const [contextLoading, setContextLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contextError, setContextError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const nextThemes = await investmentApi.listThemes();
      setThemes(nextThemes);
      setSelectedThemeId((current) => current ?? nextThemes[0]?.id ?? null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedTheme = themes.find((theme) => theme.id === selectedThemeId) ?? null;

  const loadThemeContext = useCallback(async (themeId: string) => {
    setContextLoading(true);
    setContextError(null);
    try {
      const [nextSources, nextThemeSources, nextItems, nextEdge] = await Promise.all([
        investmentApi.listSources(),
        investmentApi.listThemeSources(themeId),
        investmentApi.listItems({ themeId, limit: 8 }),
        investmentApi.getInformationEdge({ themeId, limit: 8 }),
      ]);
      setSources(nextSources);
      setThemeSources(nextThemeSources);
      setThemeItems(nextItems);
      setThemeEdge(nextEdge);
    } catch (e) {
      setContextError(e instanceof ApiError ? e.message : String(e));
      setSources([]);
      setThemeSources([]);
      setThemeItems([]);
      setThemeEdge(EMPTY_EDGE);
    } finally {
      setContextLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedThemeId) void loadThemeContext(selectedThemeId);
  }, [loadThemeContext, selectedThemeId]);

  const relatedSourceIds = new Set([
    ...themeSources.map((binding) => binding.source_id),
    ...themeItems.map((item) => item.source_id).filter(Boolean),
  ]);
  const relatedSources = sources.filter((source) => relatedSourceIds.has(source.id));

  return (
    <main className="page">
      <PageHeader
        title="主题中心"
        description="主题是投资系统的中心对象：它决定哪些信息被归类、哪些信号被聚合、哪些数据源在为这个追踪域供数。"
      />

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      <Skeleton loading={loading} active>
        {themes.length === 0 ? (
          <Empty description="暂无主题。请先创建 AI 算力、宏观、Robotaxi 等追踪域。" />
        ) : (
          <List
            grid={{ gutter: 12, xs: 1, sm: 1, md: 2, lg: 2, xl: 2 }}
            dataSource={themes}
            renderItem={(theme) => (
              <List.Item>
                <Card
                  size="small"
                  style={{
                    borderColor: selectedThemeId === theme.id ? "#1677ff" : undefined,
                  }}
                  extra={
                    <Button size="small" onClick={() => setSelectedThemeId(theme.id)}>
                      查看关系
                    </Button>
                  }
                >
                  <Space direction="vertical" size={8} style={{ width: "100%" }}>
                    <Space wrap>
                      <Typography.Text strong>{theme.name}</Typography.Text>
                      <Tag color={theme.priority === "high" ? "red" : "blue"}>
                        {theme.priority}
                      </Tag>
                      <Tag>{theme.theme_type}</Tag>
                      {!theme.enabled && <Tag>停用</Tag>}
                    </Space>
                    {theme.description && (
                      <Typography.Text type="secondary">{theme.description}</Typography.Text>
                    )}
                    <Space wrap>
                      {theme.keywords.map((keyword) => (
                        <Tag key={`kw-${theme.id}-${keyword}`} color="blue">
                          {keyword}
                        </Tag>
                      ))}
                    </Space>
                    <Space wrap>
                      {theme.entities.map((entity) => (
                        <Tag key={`entity-${theme.id}-${entity}`} color="geekblue">
                          {entity}
                        </Tag>
                      ))}
                      {theme.tickers
                        .filter((ticker) => !theme.entities.includes(ticker))
                        .map((ticker) => (
                          <Tag key={`ticker-${theme.id}-${ticker}`} color="green">
                            {ticker}
                          </Tag>
                        ))}
                    </Space>
                  </Space>
                </Card>
              </List.Item>
            )}
          />
        )}
      </Skeleton>

      {selectedTheme && (
        <Card
          title={`${selectedTheme.name}控制台`}
          style={{ marginTop: 16 }}
          extra={
            <Space>
              <Link to={`/investment/items?theme_id=${selectedTheme.id}`}>
                <Button>查看全部信息</Button>
              </Link>
              <Link to={`/investment/edge?theme_id=${selectedTheme.id}`}>
                <Button type="primary">查看信息差信号</Button>
              </Link>
            </Space>
          }
        >
          {contextError && (
            <Alert type="error" message={contextError} style={{ marginBottom: 16 }} showIcon />
          )}
          <Skeleton loading={contextLoading} active>
            <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
              <Col xs={24} md={8}>
                <Card size="small">
                  <Statistic title="关联数据源" value={relatedSourceIds.size} />
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small">
                  <Statistic title="主题信息" value={themeItems.length} />
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small">
                  <Statistic title="早期信号" value={themeEdge.top_signals.length} />
                </Card>
              </Col>
            </Row>

            <Row gutter={[16, 16]}>
              <Col xs={24} lg={8}>
                <Card size="small" title="关联数据源">
                  {relatedSources.length === 0 && themeSources.length === 0 ? (
                    <Empty description="还没有绑定或产出数据源" />
                  ) : (
                    <List
                      size="small"
                      dataSource={
                        relatedSources.length > 0
                          ? relatedSources
                          : themeSources.map((binding) => ({
                              id: binding.source_id,
                              name: binding.source_id,
                              source_type: "manual" as const,
                              workspace_id: binding.workspace_id,
                              config: {},
                              default_info_layer: "news" as const,
                              default_watchlist_ids: [],
                              poll_interval_seconds: 0,
                              enabled: binding.enabled,
                            }))
                      }
                      renderItem={(source) => (
                        <List.Item>
                          <List.Item.Meta
                            title={source.name}
                            description={
                              <Space wrap>
                                <Tag>{source.source_type}</Tag>
                                <Tag color={source.enabled ? "green" : "default"}>
                                  {source.enabled ? "启用" : "停用"}
                                </Tag>
                              </Space>
                            }
                          />
                        </List.Item>
                      )}
                    />
                  )}
                </Card>
              </Col>

              <Col xs={24} lg={8}>
                <Card size="small" title="最近主题信息">
                  {themeItems.length === 0 ? (
                    <Empty description="还没有归入这个主题的信息" />
                  ) : (
                    <List
                      size="small"
                      dataSource={themeItems}
                      renderItem={(item) => (
                        <List.Item>
                          <List.Item.Meta
                            title={item.title_zh ?? item.title}
                            description={
                              <Space direction="vertical" size={2}>
                                <Space wrap>
                                  <InfoLayerTag layer={item.info_layer} />
                                  <Typography.Text type="secondary">
                                    {item.source_name ?? "未知来源"}
                                  </Typography.Text>
                                </Space>
                                {(item.summary_zh ?? item.summary) && (
                                  <Typography.Text type="secondary" ellipsis>
                                    {item.summary_zh ?? item.summary}
                                  </Typography.Text>
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

              <Col xs={24} lg={8}>
                <Card size="small" title="主题早期信号">
                  {themeEdge.top_signals.length === 0 ? (
                    <Empty description="还没有聚合出主题信号" />
                  ) : (
                    <List
                      size="small"
                      dataSource={themeEdge.top_signals}
                      renderItem={(signal) => (
                        <List.Item>
                          <List.Item.Meta
                            title={signal.title}
                            description={
                              <Space direction="vertical" size={2}>
                                <Typography.Text>{signal.summary}</Typography.Text>
                                <Space wrap>
                                  <Tag>{signal.signal_type}</Tag>
                                  <Tag color="blue">来源 {signal.source_count}</Tag>
                                  {signal.information_edge_score != null && (
                                    <Tag color="purple">
                                      {Math.round(signal.information_edge_score * 100)}%
                                    </Tag>
                                  )}
                                </Space>
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
          </Skeleton>
        </Card>
      )}
    </main>
  );
}
