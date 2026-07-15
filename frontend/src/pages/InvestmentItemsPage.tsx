import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  message,
  Modal,
  Segmented,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { InvestmentItemDrawer } from "../components/investment/InvestmentItemDrawer";
import { ImpactTag } from "../components/investment/ImpactTag";
import { InfoLayerTag } from "../components/investment/InfoLayerTag";
import { ReviewStatusTag } from "../components/investment/ReviewStatusTag";
import { TranslationStatusTag } from "../components/investment/TranslationStatusTag";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type ActionStatus,
  type InfoLayer,
  type InvestmentItem,
} from "../services/investmentApi";

const LAYER_FILTERS = [
  { label: "全部", value: "" },
  { label: "一手", value: "primary_source" },
  { label: "宏观", value: "macro_calendar" },
  { label: "新闻", value: "news" },
  { label: "观点", value: "opinion" },
];

const STATUS_FILTERS = [
  { label: "全部", value: "" },
  { label: "待审阅", value: "pending_review" },
  { label: "跟踪中", value: "tracking" },
  { label: "已研究", value: "researched" },
  { label: "忽略", value: "ignored" },
];

function fmtDate(s?: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString("zh-CN");
  } catch {
    return s;
  }
}

export function InvestmentItemsPage() {
  const [searchParams] = useSearchParams();
  const themeId = searchParams.get("theme_id") ?? undefined;
  const [items, setItems] = useState<InvestmentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [layer, setLayer] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<InvestmentItem | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [xImportOpen, setXImportOpen] = useState(false);
  const [xImporting, setXImporting] = useState(false);
  const [xImportForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await investmentApi.listItems({
        infoLayer: (layer || undefined) as InfoLayer | undefined,
        actionStatus: (status || undefined) as ActionStatus | undefined,
        themeId,
        limit: 200,
      });
      setItems(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [layer, status, themeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleTranslate = useCallback(async () => {
    setTranslating(true);
    try {
      const result = await investmentApi.translateItems("ws_default", 100);
      message.success(`已翻译 ${result.translated} 条，跳过 ${result.skipped} 条`);
      await load();
    } catch (e) {
      const detail = e instanceof ApiError ? e.message : String(e);
      message.error(`翻译失败：${detail}`);
    } finally {
      setTranslating(false);
    }
  }, [load]);

  const handleImportX = useCallback(async () => {
    const values = await xImportForm.validateFields();
    setXImporting(true);
    try {
      await investmentApi.createItem({
        title: values.title,
        source_url: values.source_url,
        source_name: "X",
        summary: values.summary,
        info_layer: "opinion",
        source_credibility: "unverified",
        action_status: "pending_review",
      });
      message.success("X 内容已导入");
      setXImportOpen(false);
      xImportForm.resetFields();
      await load();
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setXImporting(false);
    }
  }, [load, xImportForm]);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter((i) =>
      [i.title, i.title_zh, i.summary, i.summary_zh, i.source_name]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(q)),
    );
  }, [items, search]);

  const columns: ColumnsType<InvestmentItem> = [
    {
      title: "标题",
      dataIndex: "title",
      key: "title",
      render: (_, r) => (
        <Space direction="vertical" size={0}>
          <Space size={6} wrap>
            <Typography.Link
              onClick={() => {
                setSelected(r);
                setDrawerOpen(true);
              }}
            >
              {r.title_zh ?? r.title}
            </Typography.Link>
            <TranslationStatusTag item={r} />
          </Space>
          {(r.summary_zh ?? r.summary) && (
            <Typography.Text
              type="secondary"
              ellipsis
              style={{ fontSize: 12, maxWidth: 520 }}
            >
              {r.summary_zh ?? r.summary}
            </Typography.Text>
          )}
          {r.source_url && (
            <Typography.Link
              ellipsis
              href={r.source_url}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: 12, maxWidth: 320 }}
            >
              {r.source_url}
            </Typography.Link>
          )}
        </Space>
      ),
    },
    {
      title: "层级",
      dataIndex: "info_layer",
      key: "info_layer",
      render: (l: InfoLayer) => <InfoLayerTag layer={l} />,
    },
    { title: "来源", dataIndex: "source_name", key: "source_name", width: 140 },
    {
      title: "发布时间",
      dataIndex: "published_at",
      key: "published_at",
      width: 180,
      render: fmtDate,
    },
    { title: "重要性", dataIndex: "importance", key: "importance", width: 80 },
    {
      title: "影响",
      dataIndex: "impact_direction",
      key: "impact_direction",
      width: 90,
      render: (d) => <ImpactTag direction={d} />,
    },
    {
      title: "状态",
      dataIndex: "action_status",
      key: "action_status",
      width: 100,
      render: (s: ActionStatus) => <ReviewStatusTag status={s} />,
    },
    {
      title: "操作",
      key: "actions",
      width: 100,
      render: (_, r) => (
        <Button
          type="link"
          onClick={() => {
            setSelected(r);
            setDrawerOpen(true);
          }}
        >
          查看详情
        </Button>
      ),
    },
  ];

  return (
    <main className="page">
      <PageHeader
        title="投资信息"
        description="按层级 / 状态筛选投资信息条目。"
        extra={<Button type="primary" onClick={() => setXImportOpen(true)}>导入 X 内容</Button>}
      />
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}
      <Card>
        <Space direction="vertical" style={{ width: "100%", marginBottom: 16 }}>
          <Segmented options={LAYER_FILTERS} value={layer} onChange={(v) => setLayer(String(v))} />
          <Space wrap>
            {themeId && <Tag color="blue">主题过滤：{themeId}</Tag>}
            <Segmented
              options={STATUS_FILTERS}
              value={status}
              onChange={(v) => setStatus(String(v))}
            />
            <Input.Search
              placeholder="搜索标题或来源"
              allowClear
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: 240 }}
            />
            <Button onClick={() => void load()}>刷新</Button>
            <Button loading={translating} onClick={() => void handleTranslate()}>
              翻译未翻译内容
            </Button>
          </Space>
        </Space>

        <Spin spinning={loading}>
          {filtered.length === 0 && !loading ? (
            <Empty description="暂无投资信息（创建数据源并抓取后会出现真实条目）" />
          ) : (
            <Table
              rowKey="id"
              columns={columns}
              dataSource={filtered}
              pagination={{ pageSize: 20 }}
              size="middle"
            />
          )}
        </Spin>
      </Card>

      <InvestmentItemDrawer
        item={selected}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onUpdated={() => void load()}
      />

      <Modal
        open={xImportOpen}
        title="导入 X 内容"
        onCancel={() => setXImportOpen(false)}
        onOk={() => void handleImportX()}
        okText="导入"
        cancelText="取消"
        confirmLoading={xImporting}
      >
        <Form form={xImportForm} layout="vertical">
          <Form.Item label="标题" name="title" rules={[{ required: true }]}>
            <Input placeholder="如：AI capex thread" />
          </Form.Item>
          <Form.Item label="X 链接" name="source_url" rules={[{ required: true }]}>
            <Input placeholder="https://x.com/..." />
          </Form.Item>
          <Form.Item label="正文/备注" name="summary" rules={[{ required: true }]}>
            <Input.TextArea rows={5} placeholder="粘贴推文正文、线程摘要或你的备注" />
          </Form.Item>
        </Form>
      </Modal>
    </main>
  );
}
