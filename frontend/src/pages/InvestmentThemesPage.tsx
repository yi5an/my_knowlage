import { Alert, Card, Empty, List, Skeleton, Space, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../services/client";
import { investmentApi, type InvestmentTheme } from "../services/investmentApi";

export function InvestmentThemesPage() {
  const [themes, setThemes] = useState<InvestmentTheme[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setThemes(await investmentApi.listThemes());
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
        title="主题中心"
        description="先固定追踪范围，再给每个主题配置一手源、人源账号池和验证线索。"
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
                <Card size="small">
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
    </main>
  );
}
