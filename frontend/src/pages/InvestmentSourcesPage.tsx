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
      url: values.url,
      default_info_layer: values.default_info_layer ?? "news",
      poll_interval_seconds: values.poll_interval_seconds ?? 3600,
    };
    // SEC needs a CIK in config; other types use url.
    if (sourceType === "sec_edgar") {
      payload.config = { cik: values.cik, forms: ["10-K", "10-Q", "8-K", "4"] };
      // SEC fetcher reads User-Agent from server settings, not per-source.
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
              ]}
            />
          </Form.Item>
          <Form.Item shouldUpdate={(prev, cur) => prev.source_type !== cur.source_type} noStyle>
            {({ getFieldValue }) =>
              getFieldValue("source_type") === "sec_edgar" ? (
                <Form.Item label="CIK" name="cik" rules={[{ required: true }]}>
                  <Input placeholder="如：0000320193 (Apple)" />
                </Form.Item>
              ) : (
                <Form.Item label="URL" name="url" rules={[{ required: true }]}>
                  <Input placeholder="https://www.federalreserve.gov/feeds/press_monetary.xml" />
                </Form.Item>
              )
            }
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
          <Typography.Text type="secondary">
            注意：SEC 抓取需在服务端配置 <code>SEC_USER_AGENT</code>，FRED 需配置 <code>FRED_API_KEY</code>。缺少时抓取会失败并记录错误，不会生成示例数据。
          </Typography.Text>
        </Form>
      </Modal>
    </main>
  );
}
