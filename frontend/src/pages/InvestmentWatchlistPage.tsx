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
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type InvestmentWatchlist,
} from "../services/investmentApi";

export function InvestmentWatchlistPage() {
  const [items, setItems] = useState<InvestmentWatchlist[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await investmentApi.listWatchlist());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

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

  return (
    <main className="page">
      <PageHeader
        title="观察对象"
        description="管理你关注的股票 / 公司 / 宏观主题。"
        extra={<Button type="primary" onClick={() => setOpen(true)}>添加观察对象</Button>}
      />
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}
      <Card>
        <Spin spinning={loading}>
          {items.length === 0 ? (
            <Empty description="暂无观察对象" />
          ) : (
            <List
              dataSource={items}
              renderItem={(w) => (
                <List.Item>
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
    </main>
  );
}
