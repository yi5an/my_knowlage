import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  List,
  Row,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { ArrowLeftOutlined, YoutubeOutlined, ClockCircleOutlined } from "@ant-design/icons";

import {
  getSummaryCard,
  markSummaryRead,
  youtubeTimestampUrl,
  type VideoSummaryCard,
} from "../services/youtubeApi";
import { MindmapView } from "../components/MindmapView";

const { Title, Paragraph, Text } = Typography;

export function VideoSummaryPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const [card, setCard] = useState<VideoSummaryCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!documentId) return;
    setLoading(true);
    setError(null);
    getSummaryCard(documentId)
      .then((c) => {
        setCard(c);
        // Opening the card marks the summary as read (clears the unread star
        // in the dashboard list). Fire-and-forget; a failure just means the
        // star sticks until the next open — not worth surfacing to the user.
        markSummaryRead(documentId).catch(() => {});
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [documentId]);

  if (loading) {
    return (
      <main className="page">
        <Spin size="large" />
      </main>
    );
  }
  if (error) {
    return (
      <main className="page">
        <Alert type="error" message="加载总结失败" description={error} />
      </main>
    );
  }
  if (!card || !card.summary) {
    return (
      <main className="page">
        <Empty description="暂无总结" />
      </main>
    );
  }

  const { summary, mindmap } = card;

  return (
    <main className="page">
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Link to="/youtube">
          <Button type="link" icon={<ArrowLeftOutlined />} style={{ padding: 0 }}>
            返回总结列表
          </Button>
        </Link>

        <Card>
          <Row gutter={16} align="middle">
            {card.thumbnail_url && (
              <Col>
                <img
                  src={card.thumbnail_url}
                  alt={card.title}
                  style={{ width: 160, borderRadius: 8 }}
                />
              </Col>
            )}
            <Col flex="auto">
              <Title level={3} style={{ marginBottom: 4 }}>
                {card.title}
              </Title>
              <Space size="middle">
                {card.channel_name && <Text type="secondary">{card.channel_name}</Text>}
                {card.published_at && (
                  <Text type="secondary">
                    📅 {new Date(card.published_at).toLocaleDateString("zh-CN")}
                  </Text>
                )}
                {card.duration_sec && (
                  <Text type="secondary">
                    <ClockCircleOutlined /> {Math.floor(card.duration_sec / 60)}m
                  </Text>
                )}
                <Button
                  type="link"
                  icon={<YoutubeOutlined />}
                  href={youtubeTimestampUrl(card.video_id, 0)}
                  target="_blank"
                  style={{ padding: 0 }}
                >
                  在 YouTube 观看
                </Button>
              </Space>
              <Paragraph style={{ marginTop: 12, marginBottom: 0 }}>
                <Text strong>💡 </Text>
                {summary.tldr}
              </Paragraph>
              <Space wrap style={{ marginTop: 8 }}>
                {summary.tags.map((t) => (
                  <Tag key={t} color="blue">
                    #{t}
                  </Tag>
                ))}
                {summary.transcript_source === "auto" && (
                  <Tag color="orange">自动生成字幕</Tag>
                )}
              </Space>
            </Col>
          </Row>
        </Card>

        <Tabs
          items={[
            {
              key: "summary",
              label: "总结",
              children: (
                <Row gutter={16}>
                  <Col xs={24} lg={14}>
                    <Card title="核心要点" style={{ marginBottom: 16 }}>
                      <List
                        dataSource={summary.key_points}
                        renderItem={(p) => (
                          <List.Item>
                            <Space>
                              <Text>{p.point}</Text>
                              <TimestampLink videoId={card.video_id} ts={p.timestamp} label={p.timestamp_str} />
                            </Space>
                          </List.Item>
                        )}
                      />
                    </Card>
                    <Card title="关键引用">
                      <List
                        dataSource={summary.quotes}
                        renderItem={(q) => (
                          <List.Item>
                            <Space direction="vertical" size={0}>
                              <Text italic>"{q.text}"</Text>
                              <TimestampLink videoId={card.video_id} ts={q.timestamp} label={q.timestamp_str} />
                            </Space>
                          </List.Item>
                        )}
                      />
                    </Card>
                  </Col>
                  <Col xs={24} lg={10}>
                    {summary.chapters.length > 0 && (
                      <Card title="章节大纲">
                        <List
                          dataSource={summary.chapters}
                          renderItem={(c) => (
                            <List.Item>
                              <Space>
                                <TimestampLink
                                  videoId={card.video_id}
                                  ts={c.start_sec}
                                  label={c.start_str}
                                  monospace
                                />
                                <Text>{c.title}</Text>
                              </Space>
                            </List.Item>
                          )}
                        />
                      </Card>
                    )}
                  </Col>
                </Row>
              ),
            },
            {
              key: "mindmap",
              label: "脑图",
              children: mindmap ? (
                <Card>
                  <MindmapView data={mindmap} />
                </Card>
              ) : (
                <Empty description="暂无脑图" />
              ),
            },
            {
              key: "transcript",
              label: "原字幕",
              children: card.transcript ? (
                <Card title="原始字幕">
                  <Paragraph
                    style={{
                      whiteSpace: "pre-wrap",
                      maxHeight: "60vh",
                      overflowY: "auto",
                      margin: 0,
                    }}
                  >
                    {card.transcript}
                  </Paragraph>
                </Card>
              ) : (
                <Empty description="暂无字幕" />
              ),
            },
          ]}
        />
      </Space>
    </main>
  );
}

function TimestampLink({
  videoId,
  ts,
  label,
  monospace,
}: {
  videoId: string;
  ts: number;
  label: string;
  monospace?: boolean;
}) {
  return (
    <Button
      type="link"
      size="small"
      href={youtubeTimestampUrl(videoId, ts)}
      target="_blank"
      style={monospace ? { fontFamily: "monospace", padding: 0 } : { padding: 0 }}
    >
      [{label} ↗]
    </Button>
  );
}
