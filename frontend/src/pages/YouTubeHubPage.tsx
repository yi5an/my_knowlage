import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
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
  retryVideo,
  summarizeVideo,
  youtubeThumbnailUrl,
  type SummaryListItem,
} from "../services/youtubeApi";

const { Title, Text, Paragraph } = Typography;

const HISTORY_THUMBNAIL_SHELL_STYLE: CSSProperties = {
  width: "96px",
  height: "54px",
  flex: "0 0 96px",
  borderRadius: 6,
  overflow: "hidden",
  background: "#f5f5f5",
  color: "#8c8c8c",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  position: "relative",
};

const HISTORY_THUMBNAIL_IMAGE_STYLE: CSSProperties = {
  position: "absolute",
  inset: 0,
  width: "100%",
  height: "100%",
  objectFit: "cover",
  display: "block",
};

const HISTORY_CARD_STYLE: CSSProperties = {
  minHeight: "100%",
  width: "100%",
  boxSizing: "border-box",
  border: "1px solid #f0f0f0",
  borderRadius: 8,
  background: "#fff",
  padding: 14,
  display: "flex",
  flexDirection: "column",
  gap: 10,
  overflow: "hidden",
};

const HISTORY_CARD_BODY_STYLE: CSSProperties = {
  display: "flex",
  gap: 12,
  alignItems: "flex-start",
  minWidth: 0,
};

const HISTORY_CARD_CONTENT_STYLE: CSSProperties = {
  minWidth: 0,
  maxWidth: "100%",
  flex: 1,
  overflow: "hidden",
};

const HISTORY_CARD_TITLE_ROW_STYLE: CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  gap: 6,
  flexWrap: "wrap",
  minWidth: 0,
  maxWidth: "100%",
};

const HISTORY_CARD_TITLE_LINK_STYLE: CSSProperties = {
  display: "block",
  minWidth: 0,
  maxWidth: "100%",
  flex: "1 1 180px",
};

const HISTORY_CARD_TITLE_STYLE: CSSProperties = {
  display: "-webkit-box",
  maxWidth: "100%",
  overflow: "hidden",
  overflowWrap: "anywhere",
  wordBreak: "break-word",
  whiteSpace: "normal",
  WebkitBoxOrient: "vertical",
  WebkitLineClamp: 2,
};

const HISTORY_CARD_SUMMARY_STYLE: CSSProperties = {
  margin: 0,
  fontSize: 13,
  overflowWrap: "anywhere",
  wordBreak: "break-word",
};

const HISTORY_TOPIC_SECTION_STYLE: CSSProperties = {
  borderTop: "1px solid #f0f0f0",
  paddingTop: 18,
  scrollMarginTop: 24,
};

const HISTORY_INDEX_STYLE: CSSProperties = {
  position: "sticky",
  top: 84,
  borderLeft: "1px solid #f0f0f0",
  paddingLeft: 14,
};

const HISTORY_INDEX_LINK_STYLE: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: 8,
  padding: "6px 0",
  color: "#595959",
  fontSize: 13,
  textDecoration: "none",
  borderBottom: "1px solid #f5f5f5",
};

const CHANNEL_SELECT_STYLE: CSSProperties = {
  minWidth: 180,
  height: 32,
  border: "1px solid #d9d9d9",
  borderRadius: 6,
  padding: "0 32px 0 11px",
  background: "#fff",
  color: "#262626",
};

const ALL_CHANNELS = "__all_channels__";
const UNTITLED_TOPIC = "未分类";

interface TopicGroup {
  topic: string;
  items: SummaryListItem[];
}

export function YouTubeHubPage() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [summaries, setSummaries] = useState<SummaryListItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [retrying, setRetrying] = useState<Record<string, boolean>>({});
  const [selectedChannel, setSelectedChannel] = useState(ALL_CHANNELS);

  const channelOptions = useMemo(() => {
    const channels = Array.from(
      new Set(
        summaries
          .map((item) => item.channel_name?.trim())
          .filter((channel): channel is string => Boolean(channel)),
      ),
    ).sort((a, b) => a.localeCompare(b, "zh-CN"));
    return [
      { value: ALL_CHANNELS, label: "全部博主" },
      ...channels.map((channel) => ({ value: channel, label: channel })),
    ];
  }, [summaries]);

  const filteredSummaries = useMemo(() => {
    if (selectedChannel === ALL_CHANNELS) return summaries;
    return summaries.filter((item) => item.channel_name === selectedChannel);
  }, [selectedChannel, summaries]);

  const topicGroups = useMemo(
    () => groupSummariesByTopic(filteredSummaries),
    [filteredSummaries],
  );

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
      const result = await summarizeVideo(trimmed);
      if (result.status === "ignored_live") {
        message.info("已忽略直播或预约直播，不会创建总结任务。");
        setUrl("");
        return;
      }
      message.success("已加入后台总结队列，刷新页面也会保留。");
      setUrl("");
      const latest = await listSummaries("ws_default", 50);
      setSummaries(latest);
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

  function historyThumbnail(item: SummaryListItem) {
    const thumbnailSrc = item.thumbnail_url ? youtubeThumbnailUrl(item.video_id) : null;
    return (
      <div
        data-testid="youtube-history-thumbnail-shell"
        style={HISTORY_THUMBNAIL_SHELL_STYLE}
      >
        <YoutubeOutlined style={{ fontSize: 24 }} />
        {thumbnailSrc && (
          <img
            data-testid="youtube-history-thumbnail-image"
            src={thumbnailSrc}
            alt=""
            style={HISTORY_THUMBNAIL_IMAGE_STYLE}
            onError={(event) => {
              event.currentTarget.style.display = "none";
            }}
          />
        )}
      </div>
    );
  }

  function renderHistoryCard(item: SummaryListItem) {
    const isFailed = item.summary_status === "failed";
    const isReady = item.summary_status === "completed" && item.tldr;
    return (
      <article key={item.document_id || item.video_id} style={HISTORY_CARD_STYLE}>
        <div style={HISTORY_CARD_BODY_STYLE}>
          {historyThumbnail(item)}
          <div style={HISTORY_CARD_CONTENT_STYLE}>
            <Space direction="vertical" size={6} style={{ width: "100%" }}>
              <div style={HISTORY_CARD_TITLE_ROW_STYLE}>
                {item.is_unread && (
                  <StarFilled style={{ color: "#faad14", fontSize: 13 }} />
                )}
                {isReady ? (
                  <Link
                    to={`/youtube/summary/${item.document_id}`}
                    style={HISTORY_CARD_TITLE_LINK_STYLE}
                  >
                    <strong
                      data-testid="youtube-history-card-title"
                      style={HISTORY_CARD_TITLE_STYLE}
                    >
                      {item.title}
                    </strong>
                  </Link>
                ) : (
                  <strong
                    data-testid="youtube-history-card-title"
                    style={HISTORY_CARD_TITLE_STYLE}
                  >
                    {item.title}
                  </strong>
                )}
                {statusTag(item)}
              </div>

              {(item.channel_name || item.published_at) && (
                <Space size="small" wrap>
                  {item.channel_name && (
                    <Text type="secondary">{item.channel_name}</Text>
                  )}
                  {item.published_at && (
                    <Text type="secondary">
                      {new Date(item.published_at).toLocaleDateString("zh-CN")}
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
                <Paragraph
                  type="secondary"
                  ellipsis={{ rows: 2, tooltip: item.tldr }}
                  style={HISTORY_CARD_SUMMARY_STYLE}
                >
                  {item.tldr}
                </Paragraph>
              )}

              <Space wrap size={[4, 4]}>
                {item.tags.slice(0, 5).map((tag) => (
                  <Tag key={tag} style={{ marginRight: 0 }}>
                    #{tag}
                  </Tag>
                ))}
              </Space>
            </Space>
          </div>
        </div>

        {item.retryable && (
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <Button
              size="small"
              loading={!!retrying[item.video_id]}
              onClick={() => void handleRetry(item)}
            >
              重新处理
            </Button>
          </div>
        )}
      </article>
    );
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
          <Space
            align="center"
            wrap
            style={{ width: "100%", justifyContent: "space-between", marginBottom: 16 }}
          >
            <Space size="small" wrap>
              <Text type="secondary">按博主筛选</Text>
              <select
                aria-label="博主筛选"
                value={selectedChannel}
                onChange={(event) => setSelectedChannel(event.target.value)}
                style={CHANNEL_SELECT_STYLE}
              >
                {channelOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </Space>
            <Text type="secondary">
              {filteredSummaries.length} 条内容，{topicGroups.length} 个主题
            </Text>
          </Space>
          <Spin spinning={listLoading}>
            {summaries.length === 0 && !listLoading ? (
              <Empty description="还没有总结过的视频。在上方粘贴一个 YouTube 链接试试。" />
            ) : filteredSummaries.length === 0 ? (
              <Empty description="当前博主没有匹配的视频总结。" />
            ) : (
              <Row gutter={[20, 16]} align="top">
                <Col xs={24} lg={19}>
                  <Space direction="vertical" size="large" style={{ width: "100%" }}>
                    {topicGroups.map((group, groupIndex) => (
                      <section
                        id={topicDomId(groupIndex)}
                        key={group.topic}
                        style={HISTORY_TOPIC_SECTION_STYLE}
                      >
                        <Space align="center" style={{ marginBottom: 12 }}>
                          <Title level={4} style={{ margin: 0 }}>
                            {group.topic}
                          </Title>
                          <Tag color="blue">{group.items.length} 条</Tag>
                        </Space>
                        <Row gutter={[12, 12]}>
                          {group.items.map((item) => (
                            <Col
                              xs={24}
                              xl={12}
                              key={item.document_id || item.video_id}
                            >
                              {renderHistoryCard(item)}
                            </Col>
                          ))}
                        </Row>
                      </section>
                    ))}
                  </Space>
                </Col>
                <Col xs={24} lg={5}>
                  <nav aria-label="主题索引" style={HISTORY_INDEX_STYLE}>
                    <Text strong style={{ display: "block", marginBottom: 8 }}>
                      主题索引
                    </Text>
                    {topicGroups.map((group, groupIndex) => (
                      <a
                        key={group.topic}
                        href={`#${topicDomId(groupIndex)}`}
                        style={HISTORY_INDEX_LINK_STYLE}
                      >
                        <span>{group.topic}</span>
                        <span>{group.items.length}</span>
                      </a>
                    ))}
                  </nav>
                </Col>
              </Row>
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

function groupSummariesByTopic(items: SummaryListItem[]): TopicGroup[] {
  const groups: TopicGroup[] = [];
  const indexByTopic = new Map<string, number>();
  for (const item of items) {
    const topic = primaryTopic(item);
    const index = indexByTopic.get(topic);
    if (index === undefined) {
      indexByTopic.set(topic, groups.length);
      groups.push({ topic, items: [item] });
    } else {
      groups[index].items.push(item);
    }
  }
  return groups;
}

function primaryTopic(item: SummaryListItem): string {
  return item.tags.find((tag) => tag.trim().length > 0)?.trim() || UNTITLED_TOPIC;
}

function topicDomId(index: number): string {
  return `youtube-topic-${index}`;
}
