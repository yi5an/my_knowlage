import { useEffect, useRef, useState } from "react";
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
  getSummaryStatusByVideo,
  listSubscriptions,
  triggerPoll,
  type PollResponse,
  type SummaryJobStatus,
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
  const [pollStatuses, setPollStatuses] = useState<Record<string, SummaryJobStatus>>({});
  const pollStatusesRef = useRef<Record<string, SummaryJobStatus>>({});

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
    pollStatusesRef.current = {};
    setPollStatuses({});
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

  async function refreshPollStatuses(result: PollResponse) {
    if (result.videos.length === 0) return;
    const statuses = await Promise.all(
      result.videos.map(async (video) => {
        try {
          return [video.video_id, await getSummaryStatusByVideo(video.video_id)] as const;
        } catch (e) {
          return [
            video.video_id,
            {
              video_id: video.video_id,
              status: "failed",
              error: `状态获取失败：${String(e)}`,
            } satisfies SummaryJobStatus,
          ] as const;
        }
      }),
    );
    const nextStatuses = Object.fromEntries(statuses);
    pollStatusesRef.current = nextStatuses;
    setPollStatuses(nextStatuses);
  }

  useEffect(() => {
    if (!pollResult || pollResult.videos.length === 0) return undefined;
    let cancelled = false;
    const refresh = async () => {
      if (cancelled) return;
      await refreshPollStatuses(pollResult);
    };
    void refresh();
    const timer = window.setInterval(() => {
      const active = pollResult.videos.some((video) => {
        const status = pollStatusesRef.current[video.video_id]?.status;
        return !status || status === "processing" || status === "unknown";
      });
      if (active) void refresh();
    }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [pollResult]);

  const pollStatusCounts = pollResult
    ? pollResult.videos.reduce(
        (acc, video) => {
          const status = pollStatuses[video.video_id]?.status;
          if (status === "succeeded") acc.succeeded += 1;
          else if (status === "failed" || status === "no_transcript" || status === "access_denied") {
            acc.failed += 1;
          } else acc.processing += 1;
          return acc;
        },
        { succeeded: 0, failed: 0, processing: 0 },
      )
    : { succeeded: 0, failed: 0, processing: 0 };

  function renderSummaryStatus(status?: SummaryJobStatus) {
    if (!status || status.status === "unknown" || status.status === "processing") {
      return <Tag color="processing">总结中</Tag>;
    }
    if (status.status === "succeeded") return <Tag color="success">已完成</Tag>;
    if (status.status === "access_denied") return <Tag color="default">无访问权限</Tag>;
    return <Tag color="error">总结失败</Tag>;
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
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              <Space wrap>
                <Text strong>上次轮询：</Text>
                <Text>
                  检查 {pollResult.poll_count} 个频道，发现 {pollResult.discovered} 个新视频。
                </Text>
                {pollResult.discovered > 0 && (
                  <>
                    <Tag color="success">已完成 {pollStatusCounts.succeeded}</Tag>
                    <Tag color={pollStatusCounts.failed ? "error" : "default"}>
                      失败 {pollStatusCounts.failed}
                    </Tag>
                    <Tag color={pollStatusCounts.processing ? "processing" : "default"}>
                      处理中 {pollStatusCounts.processing}
                    </Tag>
                  </>
                )}
              </Space>
              {pollResult.videos.length > 0 && (
                <List
                  size="small"
                  dataSource={pollResult.videos}
                  renderItem={(video) => {
                    const status = pollStatuses[video.video_id];
                    return (
                      <List.Item>
                        <List.Item.Meta
                          title={
                            <Space wrap>
                              <Text strong>{video.title}</Text>
                              {renderSummaryStatus(status)}
                            </Space>
                          }
                          description={
                            <Space direction="vertical" size={2}>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                {video.video_id}
                              </Text>
                              {status?.error && (
                                <Text type="danger" style={{ fontSize: 12 }}>
                                  {status.error}
                                </Text>
                              )}
                            </Space>
                          }
                        />
                      </List.Item>
                    );
                  }}
                />
              )}
            </Space>
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
