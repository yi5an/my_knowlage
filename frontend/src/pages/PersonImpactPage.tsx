import { Alert, Card, Empty, Skeleton, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ImpactSummary } from "../components/investment/ImpactSummary";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type PersonImpactEvent,
  type PersonImpactProfile,
} from "../services/investmentApi";

type JsonMap = Record<string, unknown>;

function displayError(error: unknown): string {
  return error instanceof ApiError ? error.message : String(error);
}

function objectValue(value: unknown): JsonMap | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonMap)
    : null;
}

function metric(event: PersonImpactEvent, windowKey: string, metricKey: string): number | null {
  const window = objectValue(event.windows[windowKey]);
  const value = window?.[metricKey];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function returnLabel(value: number | null): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

function qualityLabel(value: PersonImpactEvent["data_quality"]): string {
  return {
    complete: "完整",
    partial: "部分缺失",
    missing: "缺失",
    stale: "过期",
    invalid: "无效",
  }[value] ?? value;
}

function sourceUrl(event: PersonImpactEvent): string | null {
  const snapshot = objectValue(event.windows._source_snapshot);
  const url = snapshot?.source_url;
  return typeof url === "string" && url.length > 0 ? url : null;
}

function eventDuration(event: PersonImpactEvent): string {
  const metadata = objectValue(event.windows._meta);
  const start = typeof metadata?.query_start === "string" ? metadata.query_start : null;
  const end = typeof metadata?.query_end === "string" ? metadata.query_end : null;
  if (start && end) return `${start} → ${end}`;
  return Object.keys(event.windows).some((key) => /^\d+d$/.test(key)) ? "1D / 3D / 5D" : "—";
}

function eventPoints(events: PersonImpactEvent[]): Array<{ label: string; value: number }> {
  const points: Array<{ label: string; value: number }> = [];
  events.forEach((event) => {
    (["1d", "3d", "5d"] as const).forEach((windowKey) => {
      const value = metric(event, windowKey, "excess_return");
      if (value !== null) points.push({ label: `${event.symbol} ${windowKey.toUpperCase()}`, value });
    });
  });
  return points.slice(-12);
}

export function PersonImpactPage() {
  const { personId } = useParams<{ personId: string }>();
  const [profile, setProfile] = useState<PersonImpactProfile | null>(null);
  const [events, setEvents] = useState<PersonImpactEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!personId) return;
    setLoading(true);
    setError(null);
    try {
      const [nextProfile, nextEvents] = await Promise.all([
        investmentApi.getPersonImpactProfile(personId),
        investmentApi.listPersonImpactEvents(personId, 100),
      ]);
      setProfile(nextProfile);
      setEvents(nextEvents);
    } catch (e) {
      setError(displayError(e));
      setProfile(null);
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, [personId]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns = useMemo<ColumnsType<PersonImpactEvent>>(
    () => [
      {
        title: "原始 X",
        key: "source",
        render: (_, event) => {
          const url = sourceUrl(event);
          return url ? (
            <a href={url} target="_blank" rel="noreferrer">
              打开原文
            </a>
          ) : (
            <Typography.Text type="secondary">原文不可用</Typography.Text>
          );
        },
      },
      { title: "事件时间", dataIndex: "event_at", key: "event_at", render: dateLabel },
      {
        title: "标的 / 基准",
        key: "symbols",
        render: (_, event) => `${event.symbol} / ${event.benchmark_symbol}`,
      },
      {
        title: "1D",
        key: "1d",
        render: (_, event) => returnLabel(metric(event, "1d", "excess_return")),
      },
      {
        title: "3D",
        key: "3d",
        render: (_, event) => returnLabel(metric(event, "3d", "excess_return")),
      },
      {
        title: "5D",
        key: "5d",
        render: (_, event) => returnLabel(metric(event, "5d", "excess_return")),
      },
      {
        title: "成交量比",
        key: "volume",
        render: (_, event) => {
          const value = metric(event, "1d", "volume_ratio");
          return value === null ? "—" : `${value.toFixed(2)}x`;
        },
      },
      { title: "窗口 / 时段", key: "duration", render: (_, event) => eventDuration(event) },
      {
        title: "并发事件",
        key: "concurrent",
        render: (_, event) =>
          event.concurrent_events.length > 0 ? (
            <Tag color="warning">{event.concurrent_events.length} 个</Tag>
          ) : (
            <Typography.Text type="secondary">无</Typography.Text>
          ),
      },
      {
        title: "数据质量",
        dataIndex: "data_quality",
        key: "data_quality",
        render: (value: PersonImpactEvent["data_quality"]) => (
          <Tag color={value === "complete" ? "success" : "warning"}>{qualityLabel(value)}</Tag>
        ),
      },
    ],
    [],
  );

  const points = useMemo(() => eventPoints(events), [events]);
  const chartMax = Math.max(...points.map((point) => Math.abs(point.value)), 0.01);

  return (
    <main className="page investment-person-impact-page">
      <PageHeader
        title="人物影响"
        description="将公开言论与随后市场表现做事件研究，展示可复核的历史关联与数据质量。"
        extra={<Link to="/investment/accounts">返回账号发现</Link>}
      />

      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      <Skeleton loading={loading} active>
        {profile ? <ImpactSummary profile={profile} /> : !loading && <Empty description="暂无人物影响资料" />}

        {profile && !profile.sample_sufficient && (
          <Alert
            type="warning"
            showIcon
            message="样本不足"
            description="有效事件少于 5 个，当前不下影响结论；请继续积累事件与市场数据。"
            style={{ marginTop: 16 }}
          />
        )}
        {profile?.uncertainty?.includes("不可归因") && (
          <Alert
            type="warning"
            showIcon
            message="不可归因"
            description="同期存在其他重大事件或数据缺失，无法将价格变化归因于该人物言论。"
            style={{ marginTop: 16 }}
          />
        )}

        <Card title="事件明细" style={{ marginTop: 16 }}>
          {events.length === 0 ? (
            <Empty description="暂无事件研究记录" />
          ) : (
            <Table<PersonImpactEvent>
              rowKey="id"
              size="small"
              columns={columns}
              dataSource={events}
              pagination={{ pageSize: 10 }}
              scroll={{ x: 1100 }}
            />
          )}
        </Card>

        {points.length > 0 && (
          <Card title="API 返回的超额收益点" style={{ marginTop: 16 }}>
            <svg
              className="investment-impact-chart"
              role="img"
              aria-label="API 返回的超额收益趋势"
              viewBox="0 0 720 180"
              preserveAspectRatio="none"
            >
              <line x1="0" y1="90" x2="720" y2="90" stroke="#b8bec8" strokeDasharray="4 4" />
              {points.map((point, index) => {
                const x = points.length === 1 ? 360 : (index / (points.length - 1)) * 700 + 10;
                const y = 90 - (point.value / chartMax) * 70;
                return (
                  <g key={`${point.label}-${index}`}>
                    <circle cx={x} cy={y} r="4" fill={point.value >= 0 ? "#3f9b5f" : "#d16b56"} />
                    <title>{`${point.label}: ${returnLabel(point.value)}`}</title>
                  </g>
                );
              })}
            </svg>
          </Card>
        )}
      </Skeleton>

      <Typography.Paragraph type="secondary" className="investment-person-impact-page__note">
        免责声明：历史关联不等于因果关系，也不代表未来收益。事件重叠、同期事件、复权方式、交易日历和数据缺失都会影响结果，请结合原始 X 内容独立判断。
      </Typography.Paragraph>
    </main>
  );
}
