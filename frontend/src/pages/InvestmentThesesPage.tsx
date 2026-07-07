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
import { WatchlistSelector } from "../components/investment/WatchlistSelector";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type InvestmentThesis,
  type InvestmentWatchlist,
} from "../services/investmentApi";

export function InvestmentThesesPage() {
  const [theses, setTheses] = useState<InvestmentThesis[]>([]);
  const [watchlists, setWatchlists] = useState<InvestmentWatchlist[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [t, w] = await Promise.all([
        investmentApi.listTheses(),
        investmentApi.listWatchlist(),
      ]);
      setTheses(t);
      setWatchlists(w);
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
    await investmentApi.createThesis({
      title: values.title,
      body: values.body,
      watchlist_id: values.watchlist_id,
      status: values.status ?? "open",
      confidence: values.confidence ?? "medium",
    });
    setOpen(false);
    form.resetFields();
    void load();
  };

  return (
    <main className="page">
      <PageHeader
        title="投资假设"
        description="记录并跟踪你的投资假设，信息会按对假设的影响被打分。"
        extra={<Button type="primary" onClick={() => setOpen(true)}>添加假设</Button>}
      />
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}
      <Card>
        <Spin spinning={loading}>
          {theses.length === 0 ? (
            <Empty description="暂无投资假设" />
          ) : (
            <List
              dataSource={theses}
              renderItem={(t) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space>
                        <Typography.Text strong>{t.title}</Typography.Text>
                        <Tag>{t.status}</Tag>
                        <Tag color={t.confidence === "high" ? "green" : "default"}>
                          信心：{t.confidence}
                        </Tag>
                      </Space>
                    }
                    description={t.body}
                  />
                </List.Item>
              )}
            />
          )}
        </Spin>
      </Card>

      <Modal
        open={open}
        title="添加投资假设"
        onCancel={() => setOpen(false)}
        onOk={handleCreate}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item label="标题" name="title" rules={[{ required: true }]}>
            <Input placeholder="如：AI 需求持续强劲" />
          </Form.Item>
          <Form.Item label="关联观察对象" name="watchlist_id">
            <WatchlistSelector watchlists={watchlists} />
          </Form.Item>
          <Form.Item label="状态" name="status" initialValue="open">
            <Select
              options={[
                { value: "open", label: "进行中" },
                { value: "closed", label: "已关闭" },
                { value: "invalidated", label: "已证伪" },
              ]}
            />
          </Form.Item>
          <Form.Item label="信心" name="confidence" initialValue="medium">
            <Select
              options={[
                { value: "low", label: "低" },
                { value: "medium", label: "中" },
                { value: "high", label: "高" },
              ]}
            />
          </Form.Item>
          <Form.Item label="假设内容" name="body">
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>
    </main>
  );
}
