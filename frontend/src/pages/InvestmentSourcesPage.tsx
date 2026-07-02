import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useRef, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type InvestmentSource,
  type SourceType,
} from "../services/investmentApi";

const TYPE_LABEL: Record<SourceType, string> = {
  rss: "RSS",
  sec_edgar: "SEC EDGAR",
  federal_reserve_rss: "美联储 RSS",
  bls: "BLS",
  fred: "FRED",
  hkex: "港交所 HKEX",
  cninfo: "巨潮 CNINFO",
  manual: "手动",
};

/** Split a textarea (one series ID per line, also tolerates commas/spaces). */
function _splitSeries(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.filter(Boolean);
  if (typeof raw !== "string") return [];
  return raw
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function fmtDate(s?: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString("zh-CN");
  } catch {
    return s;
  }
}

export function InvestmentSourcesPage() {
  const [sources, setSources] = useState<InvestmentSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [polling, setPolling] = useState<Record<string, boolean>>({});
  const [form] = Form.useForm();
  const timers = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSources(await investmentApi.listSources());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const t = timers.current;
    return () => {
      Object.values(t).forEach(clearInterval);
    };
  }, [load]);

  const handleCreate = async () => {
    const values = await form.validateFields();
    const sourceType = values.source_type as SourceType;
    const payload: Parameters<typeof investmentApi.createSource>[0] = {
      source_type: sourceType,
      name: values.name,
      default_info_layer: values.default_info_layer ?? "news",
      poll_interval_seconds: values.poll_interval_seconds ?? 3600,
    };
    // SEC needs a CIK in config; BLS/FRED need series IDs in config;
    // rss/federal_reserve_rss/hkex/cninfo use url.
    if (sourceType === "sec_edgar") {
      payload.config = { cik: values.cik, forms: ["10-K", "10-Q", "8-K", "4"] };
    } else if (sourceType === "bls") {
      payload.config = {
        series: _splitSeries(values.series),
        years: values.years ?? 1,
      };
    } else if (sourceType === "fred") {
      payload.config = {
        series: _splitSeries(values.series),
        limit: values.limit ?? 5,
      };
    } else {
      payload.url = values.url;
    }
    try {
      await investmentApi.createSource(payload);
      message.success("数据源已创建");
      setOpen(false);
      form.resetFields();
      void load();
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : String(e));
    }
  };

  /** Enqueue a fetch and poll the job until it settles, then refresh. */
  const handlePoll = async (source: InvestmentSource) => {
    setPolling((p) => ({ ...p, [source.id]: true }));
    try {
      const { job_id } = await investmentApi.pollSource(source.id);
      // Poll the job every 1.5s until done.
      timers.current[source.id] = setInterval(async () => {
        try {
          const job = await investmentApi.getFetchJob(job_id);
          if (job.status === "succeeded" || job.status === "failed") {
            clearInterval(timers.current[source.id]);
            delete timers.current[source.id];
            setPolling((p) => ({ ...p, [source.id]: false }));
            if (job.status === "succeeded") {
              message.success(
                `抓取完成：新增 ${job.items_created} 条（共见 ${job.items_seen}）`,
              );
            } else {
              message.error(job.last_error ? `抓取失败：${job.last_error}` : "抓取失败");
            }
            void load();
          }
        } catch (e) {
          clearInterval(timers.current[source.id]);
          delete timers.current[source.id];
          setPolling((p) => ({ ...p, [source.id]: false }));
          message.error(e instanceof ApiError ? e.message : String(e));
        }
      }, 1500);
    } catch (e) {
      setPolling((p) => ({ ...p, [source.id]: false }));
      message.error(e instanceof ApiError ? e.message : String(e));
    }
  };

  const columns: ColumnsType<InvestmentSource> = [
    { title: "名称", dataIndex: "name", key: "name" },
    {
      title: "类型",
      dataIndex: "source_type",
      key: "source_type",
      render: (t: SourceType) => <Tag>{TYPE_LABEL[t] ?? t}</Tag>,
    },
    { title: "默认层级", dataIndex: "default_info_layer", key: "default_info_layer", width: 110 },
    {
      title: "抓取频率(秒)",
      dataIndex: "poll_interval_seconds",
      key: "poll_interval_seconds",
      width: 110,
    },
    {
      title: "上次抓取",
      dataIndex: "last_polled_at",
      key: "last_polled_at",
      width: 170,
      render: fmtDate,
    },
    {
      title: "下次抓取",
      dataIndex: "next_poll_at",
      key: "next_poll_at",
      width: 170,
      render: fmtDate,
    },
    {
      title: "状态",
      key: "status",
      width: 120,
      render: (_, r) =>
        r.enabled ? (
          <Tag color="success">启用</Tag>
        ) : (
          <Tag>停用</Tag>
        ),
    },
    {
      title: "操作",
      key: "actions",
      width: 120,
      render: (_, r) => (
        <Button
          size="small"
          type="primary"
          loading={!!polling[r.id]}
          onClick={() => void handlePoll(r)}
        >
          立即抓取
        </Button>
      ),
    },
  ];

  return (
    <main className="page">
      <PageHeader
        title="数据源"
        description="配置真实数据源（SEC / 美联储 / RSS）。无配置时不显示任何示例数据。"
        extra={<Button type="primary" onClick={() => setOpen(true)}>新增数据源</Button>}
      />
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}
      <Card>
        <Spin spinning={loading}>
          {sources.length === 0 && !loading ? (
            <Empty description="暂无数据源。创建一个 SEC 或 RSS 数据源后点击「立即抓取」。" />
          ) : (
            <Table
              rowKey="id"
              columns={columns}
              dataSource={sources}
              pagination={{ pageSize: 20 }}
              size="middle"
              expandable={{
                expandedRowRender: (r) =>
                  r.last_error ? (
                    <Typography.Text type="danger">最近错误：{r.last_error}</Typography.Text>
                  ) : (
                    <Typography.Text type="secondary">无最近错误</Typography.Text>
                  ),
              }}
            />
          )}
        </Spin>
      </Card>

      <Modal
        open={open}
        title="新增数据源"
        onCancel={() => setOpen(false)}
        onOk={handleCreate}
        okText="创建"
        cancelText="取消"
        width={560}
      >
        <Form form={form} layout="vertical" initialValues={{ default_info_layer: "news", poll_interval_seconds: 3600 }}>
          <Form.Item label="名称" name="name" rules={[{ required: true }]}>
            <Input placeholder="如：Apple SEC Filings" />
          </Form.Item>
          <Form.Item label="类型" name="source_type" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "rss", label: "RSS / Atom" },
                { value: "federal_reserve_rss", label: "美联储 RSS" },
                { value: "sec_edgar", label: "SEC EDGAR（按 CIK）" },
                { value: "bls", label: "BLS（按序列，宏观）" },
                { value: "fred", label: "FRED（按序列，宏观）" },
                { value: "hkex", label: "港交所 HKEX（公告搜索）" },
                { value: "cninfo", label: "巨潮 CNINFO（公告搜索）" },
              ]}
            />
          </Form.Item>
          <Form.Item shouldUpdate={(prev, cur) => prev.source_type !== cur.source_type} noStyle>
            {({ getFieldValue }) => {
              const st = getFieldValue("source_type") as SourceType;
              if (st === "sec_edgar") {
                return (
                  <Form.Item label="CIK" name="cik" rules={[{ required: true }]}>
                    <Input placeholder="如：0000320193 (Apple)" />
                  </Form.Item>
                );
              }
              if (st === "bls" || st === "fred") {
                return (
                  <>
                    <Form.Item
                      label="序列 ID（每行一个）"
                      name="series"
                      rules={[{ required: true }]}
                    >
                      <Input.TextArea
                        rows={3}
                        placeholder={
                          st === "bls"
                            ? "CUSR0000SA0&#10;LNS14000000&#10;CES0000000001"
                            : "DGS10&#10;FEDFUNDS&#10;UNRATE"
                        }
                      />
                    </Form.Item>
                    {st === "bls" ? (
                      <Form.Item label="回溯年数" name="years" initialValue={1}>
                        <InputNumber min={1} max={10} style={{ width: "100%" }} />
                      </Form.Item>
                    ) : (
                      <Form.Item label="每个序列取最近几条" name="limit" initialValue={5}>
                        <InputNumber min={1} max={100} style={{ width: "100%" }} />
                      </Form.Item>
                    )}
                  </>
                );
              }
              // rss / federal_reserve_rss / hkex / cninfo → URL
              return (
                <Form.Item label="URL" name="url" rules={[{ required: true }]}>
                  <Input placeholder="https://www.federalreserve.gov/feeds/press_monetary.xml" />
                </Form.Item>
              );
            }}
          </Form.Item>
          <Form.Item label="默认信息层级" name="default_info_layer">
            <Select
              options={[
                { value: "primary_source", label: "一手信息" },
                { value: "macro_calendar", label: "宏观" },
                { value: "news", label: "新闻" },
                { value: "opinion", label: "观点" },
              ]}
            />
          </Form.Item>
          <Form.Item label="抓取频率(秒)" name="poll_interval_seconds">
            <InputNumber min={60} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item shouldUpdate={(prev, cur) => prev.source_type !== cur.source_type} noStyle>
            {({ getFieldValue }) => {
              const st = getFieldValue("source_type") as SourceType;
              const hints: string[] = [];
              if (st === "sec_edgar") hints.push("SEC 抓取需在服务端配置 SEC_USER_AGENT");
              if (st === "fred") hints.push("FRED 抓取需在服务端配置 FRED_API_KEY");
              if (hints.length === 0) return null;
              return (
                <Typography.Text type="secondary">
                  注意：{hints.join("；")}。缺少时抓取会失败并记录错误，不会生成示例数据。
                </Typography.Text>
              );
            }}
          </Form.Item>
        </Form>
      </Modal>
    </main>
  );
}
