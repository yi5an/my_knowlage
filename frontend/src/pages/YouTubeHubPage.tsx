import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {

  Button,
  Card,
  Col,
  Empty,
  Input,
  List,
  message,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import {
  LinkOutlined,
  StarFilled,
  ThunderboltOutlined,
  YoutubeOutlined,
} from "@ant-design/icons";

import {
  listSummaries,
  pollSummaryUntilDone,
  retryVideo,
  summarizeVideo,
  type SummaryListItem,
} from "../services/youtubeApi";

const { Title, Text, Paragraph } = Typography;

export function YouTubeHubPage() {
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [summaries, setSummaries] = useState<SummaryListItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [retrying, setRetrying] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setListLoading(true);
    listSummaries("ws_default", 50)
      .then(setSummaries)
      .catch(() => {})
      .finally(() => setListLoading(false));
  }, []);

  async function handleSummarize() {
    const trimmed = url.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      // Non-blocking: backend returns immediately, runs pipeline in background.
      const submitted = await summarizeVideo(trimmed);
      message.info(
        "已提交,正在后台处理(无字幕视频会先用语音识别转写,可能需要几分钟)…",
      );
      const documentId = await pollSummaryUntilDone(submitted.video_id);
      message.success("总结完成！");
      // Refresh the list so the new summary appears before navigating.
      listSummaries("ws_default", 50).then(setSummaries).catch(() => {});
      navigate(`/youtube/summary/${documentId}`);
    } catch (e) {
      const msg = String(e);
      if (msg.includes("no_transcript") || msg.includes("没有字幕")) {
        message.error("该视频没有字幕,且语音识别不可用,无法总结。");
      } else {
        message.error("总结失败:" + msg);
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleRetry(item: SummaryListItem) {
    if (!item.video_id) return;
    setRetrying((prev) => ({ ...prev, [item.video_id]: true }));
    try {
      await retryVideo(item.video_id);
      message.success("已重新提交，后台处理中。");
      listSummaries("ws_default", 50).then(setSummaries).catch(() => {});
    } catch (e) {
      message.error("重新处理失败:" + String(e));
    } finally {
      setRetrying((prev) => ({ ...prev, [item.video_id]: false }));
    }
  }

  function statusTag(item: SummaryListItem) {
    if (item.summary_status === "completed" && item.tldr) return null;
    // Permanently inaccessible (members-only / private / deleted / geo-blocked).
    // Distinct from "转写失败" so the user knows not to retry.
    if (item.summary_status === "access_denied")
      return <Tag color="default">无访问权限</Tag>;
    if (item.summary_status === "failed") {
      if (item.failure_stage === "capture") return <Tag color="red">采集失败</Tag>;
      if (item.failure_stage === "transcript") return <Tag color="red">转写失败</Tag>;
      return <Tag color="red">总结失败</Tag>;
    }
    if (item.failure_stage === "pending") return <Tag color="warning">待处理</Tag>;
    if (item.summary_status === "no_transcript") return <Tag color="orange">无字幕</Tag>;
    return <Tag color="processing">处理中</Tag>;
  }

  return (
    <main className="page">
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <div>
          <Title level={2} style={{ marginBottom: 4 }}>
            <YoutubeOutlined /> YouTube 视频总结
          </Title>
          <Text type="secondary">
            粘贴任意 YouTube 链接，立即获取带时间戳的视频总结。
          </Text>
        </div>

        <Card>
          <Paragraph type="secondary" style={{ marginBottom: 12 }}>
            <ThunderboltOutlined /> 手动总结 —— 支持任何带字幕的公开视频。
          </Paragraph>
          <Space.Compact style={{ width: "100%" }}>
            <Input
              size="large"
              placeholder="https://www.youtube.com/watch?v=..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onPressEnter={handleSummarize}
              prefix={<LinkOutlined />}
            />
            <Button
              type="primary"
              size="large"
              loading={busy}
              onClick={handleSummarize}
            >
              总结
            </Button>
          </Space.Compact>

          {busy && (
            <div style={{ marginTop: 16 }}>
              <Spin tip="正在后台处理:获取字幕/语音识别 → 翻译 → 总结 → 抽取实体…" />
            </div>
          )}
        </Card>

        <Card
          title="历史总结"
          extra={<Link to="/youtube/subscriptions">订阅管理</Link>}
        >
          <Spin spinning={listLoading}>
            {summaries.length === 0 && !listLoading ? (
              <Empty description="还没有总结过的视频。在上方粘贴一个 YouTube 链接试试。" />
            ) : (
              <List
                dataSource={summaries}
                renderItem={(item) => {
                  const isFailed = item.summary_status === "failed";
                  const isReady = item.summary_status === "completed" && item.tldr;
                  return (
                    <List.Item
                      key={item.document_id || item.video_id}
                      actions={
                        item.retryable
                          ? [
                              <Button
                                key="retry"
                                size="small"
                                loading={!!retrying[item.video_id]}
                                onClick={() => void handleRetry(item)}
                              >
                                重新处理
                              </Button>,
                            ]
                          : undefined
                      }
                    >
                      <List.Item.Meta
                        avatar={
                          item.thumbnail_url ? (
                            <img
                              src={item.thumbnail_url}
                              alt={item.title}
                              style={{ width: 96, borderRadius: 6 }}
                            />
                          ) : (
                            <YoutubeOutlined style={{ fontSize: 32 }} />
                          )
                        }
                        title={
                          <Space size={6} wrap>
                            {item.is_unread && (
                              <StarFilled
                                style={{ color: "#faad14", fontSize: 13 }}
                              />
                            )}
                            {isReady ? (
                              <Link to={`/youtube/summary/${item.document_id}`}>
                                {item.title}
                              </Link>
                            ) : (
                              <Text strong>{item.title}</Text>
                            )}
                            {statusTag(item)}
                          </Space>
                        }
                        description={
                          <Space direction="vertical" size={0} style={{ width: "100%" }}>
                            {(item.channel_name || item.published_at) && (
                              <Space size="small" wrap>
                                {item.channel_name && (
                                  <Text type="secondary">{item.channel_name}</Text>
                                )}
                                {item.published_at && (
                                  <Text type="secondary">
                                    📅 {new Date(item.published_at).toLocaleDateString("zh-CN")}
                                  </Text>
                                )}
                              </Space>
                            )}
                            {isFailed && item.error && (
                              <Text
                                type="danger"
                                style={{ fontSize: 13 }}
                                ellipsis={{ tooltip: item.error }}
                              >
                                {item.error}
                              </Text>
                            )}
                            {item.tldr && (
                              <Text
                                type="secondary"
                                style={{ fontSize: 13 }}
                                ellipsis={{ tooltip: item.tldr }}
                              >
                                {item.tldr}
                              </Text>
                            )}
                            <Space wrap size={[4, 4]} style={{ marginTop: 2 }}>
                              {item.tags.slice(0, 4).map((t) => (
                                <Tag key={t} style={{ marginRight: 0 }}>
                                  #{t}
                                </Tag>
                              ))}
                            </Space>
                          </Space>
                        }
                      />
                    </List.Item>
                  );
                }}
              />
            )}
          </Spin>
        </Card>

        <Row gutter={16}>
          <Col xs={24} lg={12}>
            <Card title="工作原理">
              <List
                size="small"
                dataSource={[
                  "通过 YouTube Data API 获取视频元数据与章节",
                  "提取带时间戳的字幕（人工或自动生成）",
                  "无字幕时自动用语音识别（GLM-ASR）转写",
                  "用大模型总结 —— 要点与引用均带时间戳",
                  "抽取实体与关系，构建知识图谱",
                ]}
                renderItem={(item) => (
                  <List.Item>
                    <Tag color="green">✓</Tag> {item}
                  </List.Item>
                )}
              />
            </Card>
          </Col>
        </Row>
      </Space>
    </main>
  );
}
