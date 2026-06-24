import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  List,
  message,
  Modal,
  Popconfirm,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import {
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  YoutubeOutlined,
} from "@ant-design/icons";

import {
  createSubscription,
  deleteSubscription,
  listSubscriptions,
  triggerPoll,
  type PollResponse,
  type Subscription,
} from "../services/youtubeApi";

const { Title, Text } = Typography;

export function SubscriptionPage() {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [form] = Form.useForm();
  const [polling, setPolling] = useState(false);
  const [pollResult, setPollResult] = useState<PollResponse | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setSubs(await listSubscriptions());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleAdd() {
    const values = await form.validateFields();
    try {
      await createSubscription(values.channelId, {
        channelName: values.channelName,
        pollInterval: values.pollInterval,
      });
      message.success("订阅已添加");
      setAddOpen(false);
      form.resetFields();
      load();
    } catch (e) {
      message.error("添加订阅失败：" + String(e));
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteSubscription(id);
      message.success("已删除");
      load();
    } catch (e) {
      message.error("删除失败：" + String(e));
    }
  }

  async function handlePoll() {
    setPolling(true);
    setPollResult(null);
    try {
      const result = await triggerPoll();
      setPollResult(result);
      if (result.discovered > 0) {
        message.success(`发现 ${result.discovered} 个新视频，正在后台总结…`);
      } else {
        message.info("轮询完成，没有新视频。");
      }
      load();
    } catch (e) {
      message.error("轮询失败：" + String(e));
    } finally {
      setPolling(false);
    }
  }

  return (
    <main className="page">
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Title level={2} style={{ marginBottom: 4 }}>
              <YoutubeOutlined /> 订阅管理
            </Title>
            <Text type="secondary">已订阅的 YouTube 频道，将自动总结其更新。</Text>
          </Col>
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} loading={polling} onClick={handlePoll}>
                立即轮询
              </Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
                添加订阅
              </Button>
            </Space>
          </Col>
        </Row>

        {error && <Alert type="error" message="加载失败" description={error} />}

        {pollResult && (
          <Card size="small">
            <Text strong>上次轮询：</Text>
            <Text>
              {" "}检查 {pollResult.poll_count} 个频道，发现 {pollResult.discovered} 个新视频。
            </Text>
            {pollResult.discovered > 0 && (
              <Tag color="processing" style={{ marginLeft: 8 }}>
                后台总结中…
              </Tag>
            )}
          </Card>
        )}

        <Card loading={loading}>
          <Spin spinning={loading && subs.length === 0}>
            <List
              dataSource={subs}
              locale={{ emptyText: "暂无订阅。添加一个 YouTube 频道即可开始。" }}
              renderItem={(sub) => (
                <List.Item
                  actions={[
                    <Popconfirm
                      key="delete"
                      title="确定删除该订阅？"
                      onConfirm={() => handleDelete(sub.id)}
                    >
                      <Button danger icon={<DeleteOutlined />} size="small">
                        删除
                      </Button>
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={<YoutubeOutlined style={{ fontSize: 24 }} />}
                    title={
                      <Space>
                        {sub.channel_name || sub.channel_id}
                        {sub.enabled ? (
                          <Tag color="green">已启用</Tag>
                        ) : (
                          <Tag color="default">已暂停</Tag>
                        )}
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={0}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          频道：{sub.channel_id}
                        </Text>
                        <Space size="large">
                          <Text type="secondary">
                            间隔：每 {Math.round(sub.poll_interval / 60)} 分钟
                          </Text>
                          {sub.last_polled_at && (
                            <Text type="secondary">
                              上次轮询：{new Date(sub.last_polled_at).toLocaleString()}
                            </Text>
                          )}
                        </Space>
                        {sub.last_error && (
                          <Text type="danger" style={{ fontSize: 12 }}>
                            上次错误：{sub.last_error}
                          </Text>
                        )}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Spin>
        </Card>

        <Modal
          title="添加 YouTube 订阅"
          open={addOpen}
          onOk={handleAdd}
          onCancel={() => setAddOpen(false)}
          okText="添加"
          cancelText="取消"
        >
          <Form form={form} layout="vertical" initialValues={{ pollInterval: 3600 }}>
            <Form.Item
              name="channelId"
              label="频道 ID 或链接"
              rules={[{ required: true, message: "请输入频道 ID 或链接" }]}
            >
              <Input placeholder="UC... 或 https://www.youtube.com/@频道名" />
            </Form.Item>
            <Form.Item name="channelName" label="显示名称（可选）">
              <Input placeholder="AI 频道" />
            </Form.Item>
            <Form.Item name="pollInterval" label="轮询间隔（秒）">
              <InputNumber min={300} style={{ width: "100%" }} />
            </Form.Item>
          </Form>
        </Modal>
      </Space>
    </main>
  );
}
