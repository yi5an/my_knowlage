import { Alert, Card, Empty, List, Skeleton, Space, Statistic, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { InformationEdgeCard } from "../components/investment/InformationEdgeCard";
import { PageHeader } from "../components/PageHeader";
import { useOptionalCompanion } from "../components/companion/companionContext";
import { ApiError } from "../services/client";
import { investmentApi, type InformationEdgeDigest, type InvestmentSignal } from "../services/investmentApi";

const EMPTY_DIGEST: InformationEdgeDigest = {
  generated_at: "",
  top_signals: [],
  source_traces: [],
  unvalidated_signals: [],
  stale_or_noise: [],
};

export function InformationEdgePage() {
  const [searchParams] = useSearchParams();
  const companion = useOptionalCompanion();
  const setCompanionContext = companion?.setContext;
  const clearCompanionContext = companion?.clearContext;
  const themeId = searchParams.get("theme_id") ?? undefined;
  const [digest, setDigest] = useState<InformationEdgeDigest>(EMPTY_DIGEST);
  const [selectedSignal, setSelectedSignal] = useState<InvestmentSignal | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDigest(await investmentApi.getInformationEdge({ themeId, limit: 20 }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [themeId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedSignal || !setCompanionContext) return;
    setCompanionContext({
      workspaceId: selectedSignal.workspace_id,
      subjectType: "information_edge",
      subjectId: selectedSignal.id,
      title: selectedSignal.title,
    });
    return () => clearCompanionContext?.(selectedSignal.id);
  }, [clearCompanionContext, selectedSignal, setCompanionContext]);

  return (
    <main className="page">
      <PageHeader
        title="信息差系统"
        description="按固定主题追踪一手源、人源观点、新闻确认和市场反馈，优先展示尚未充分验证的早期信号。"
      />

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      <Skeleton loading={loading} active>
        {themeId && (
          <Space style={{ marginBottom: 16 }}>
            <Tag color="blue">主题过滤：{themeId}</Tag>
          </Space>
        )}

        <Space size={16} wrap style={{ marginBottom: 16 }}>
          <Card>
            <Statistic title="高分信号" value={digest.top_signals.length} />
          </Card>
          <Card>
            <Statistic title="待验证" value={digest.unvalidated_signals.length} />
          </Card>
          <Card>
            <Statistic title="来源追踪" value={digest.source_traces.length} />
          </Card>
        </Space>

        <section style={{ marginBottom: 16 }}>
          <Typography.Title level={4}>早期信号</Typography.Title>
          {digest.top_signals.length === 0 ? (
            <Empty description="暂无信息差信号" />
          ) : (
            <List
              grid={{ gutter: 12, column: 1 }}
              dataSource={digest.top_signals}
              renderItem={(signal) => (
                <List.Item>
                  <InformationEdgeCard signal={signal} onSelect={setSelectedSignal} />
                </List.Item>
              )}
            />
          )}
        </section>

        <section>
          <Typography.Title level={4}>来源追踪</Typography.Title>
          {digest.source_traces.length === 0 ? (
            <Empty description="暂无反推来源" />
          ) : (
            <List
              dataSource={digest.source_traces}
              renderItem={(trace) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space wrap>
                        <Tag color={trace.trace_type === "likely_source" ? "green" : "blue"}>
                          {trace.trace_type}
                        </Tag>
                        {trace.lead_time_hours != null && (
                          <Tag color="purple">来源领先 {trace.lead_time_hours} 小时</Tag>
                        )}
                        <Typography.Text>置信度 {Math.round(trace.confidence * 100)}%</Typography.Text>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={4}>
                        <Typography.Text>{trace.match_reason}</Typography.Text>
                        {trace.matched_fact && (
                          <Typography.Text type="secondary">
                            匹配：{trace.matched_fact}
                          </Typography.Text>
                        )}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </section>
      </Skeleton>
    </main>
  );
}
