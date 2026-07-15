import {
  Alert,
  Card,
  Empty,
  Segmented,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { InfoLayerTag } from "../components/investment/InfoLayerTag";
import { TranslationStatusTag } from "../components/investment/TranslationStatusTag";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type Importance,
  type InvestmentItem,
} from "../services/investmentApi";

const IMPORTANCE_FILTERS = [
  { label: "全部", value: "" },
  { label: "高", value: "high" },
  { label: "中", value: "medium" },
  { label: "低", value: "low" },
];

const DAY_FILTERS = [
  { label: "近 7 天", value: "7" },
  { label: "近 30 天", value: "30" },
  { label: "近 90 天", value: "90" },
];

const IMPORTANCE_COLOR: Record<string, string> = {
  high: "red",
  medium: "orange",
  low: "default",
};

function fmtDate(s?: string | null): string {
  if (!s) return "未注明时间";
  try {
    return new Date(s).toLocaleString("zh-CN");
  } catch {
    return s;
  }
}

function dayKey(s?: string | null): string {
  if (!s) return "未注明日期";
  try {
    return new Date(s).toLocaleDateString("zh-CN");
  } catch {
    return "未注明日期";
  }
}

export function InvestmentCalendarPage() {
  const [items, setItems] = useState<InvestmentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importance, setImportance] = useState("");
  const [days, setDays] = useState("30");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(
        await investmentApi.listMacroEvents({
          days: Number(days),
          importance: (importance || undefined) as Importance | undefined,
        }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [importance, days]);

  useEffect(() => {
    void load();
  }, [load]);

  // Group items by their published date for the timeline.
  const grouped = useMemo(() => {
    const map = new Map<string, InvestmentItem[]>();
    for (const it of items) {
      const key = dayKey(it.published_at);
      const arr = map.get(key) ?? [];
      arr.push(it);
      map.set(key, arr);
    }
    return Array.from(map.entries());
  }, [items]);

  return (
    <main className="page">
      <PageHeader
        title="宏观日历"
        description="宏观经济与政策事件时间线（来自美联储 RSS 等宏观信息源）。"
      />
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}
      <Card>
        <Space direction="vertical" style={{ width: "100%", marginBottom: 16 }}>
          <Space wrap>
            <Segmented
              options={IMPORTANCE_FILTERS}
              value={importance}
              onChange={(v) => setImportance(String(v))}
            />
            <Segmented
              options={DAY_FILTERS}
              value={days}
              onChange={(v) => setDays(String(v))}
            />
          </Space>
        </Space>

        <Spin spinning={loading}>
          {grouped.length === 0 && !loading ? (
            <Empty description="暂无宏观事件（抓取美联储 RSS / BLS / FRED 后会出现）" />
          ) : (
            <Timeline
              items={grouped.map(([date, group]) => ({
                color: "blue",
                children: (
                  <div>
                    <Typography.Text strong>{date}</Typography.Text>
                    <div style={{ marginTop: 8 }}>
                      {group.map((item) => (
                        <div
                          key={item.id}
                          style={{ marginBottom: 12, paddingLeft: 4 }}
                        >
                          <Space wrap>
                            <InfoLayerTag layer={item.info_layer} />
                            <Tag color={IMPORTANCE_COLOR[item.importance] ?? "default"}>
                              {item.importance}
                            </Tag>
                            <Typography.Text type="secondary">
                              {fmtDate(item.published_at)}
                            </Typography.Text>
                            {item.source_name && <Tag>{item.source_name}</Tag>}
                            <TranslationStatusTag item={item} />
                          </Space>
                          <div style={{ marginTop: 4 }}>
                            <Typography.Text>{item.title_zh ?? item.title}</Typography.Text>
                          </div>
                          {(item.summary_zh ?? item.summary) && (
                            <Typography.Paragraph
                              type="secondary"
                              ellipsis={{ rows: 2 }}
                              style={{ marginTop: 4, marginBottom: 0 }}
                            >
                              {item.summary_zh ?? item.summary}
                            </Typography.Paragraph>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ),
              }))}
            />
          )}
        </Spin>
      </Card>
    </main>
  );
}
