import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Alert,
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
  Statistic,
  Tag,
  Typography,
} from "antd";
import {
  ClockCircleOutlined,
  LinkOutlined,
  NodeIndexOutlined,
  StarFilled,
  ThunderboltOutlined,
  YoutubeOutlined,
} from "@ant-design/icons";

import { PageHeader } from "../components/PageHeader";
import {
  getDashboardStats,
  listSummaries,
  pollSummaryUntilDone,
  summarizeVideo,
  type DashboardStats,
  type SummaryListItem,
} from "../services/youtubeApi";

const { Text } = Typography;

const EMPTY_STATS: DashboardStats = {
  subscriptions: 0,
  summarized_videos: 0,
  pending_videos: 0,
  entities: 0,
  relations: 0,
};

export function DashboardPage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats>(EMPTY_STATS);
  const [summaries, setSummaries] = useState<SummaryListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summaryUrl, setSummaryUrl] = useState("");
  const [summarizing, setSummarizing] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([getDashboardStats(), listSummaries("ws_default", 10)])
      .then(([s, list]) => {
        setStats(s);
        setSummaries(list);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  async function handleSummarize() {
    const url = summaryUrl.trim();
    if (!url) return;
    setSummarizing(true);
    try {
      // Non-blocking submit: backend returns immediately with status=processing,
      // then runs transcript/ASR/translation/summary in a background thread.
      const submitted = await summarizeVideo(url);
      message.info("已提交,正在后台处理(无字幕视频会先用语音识别转写,可能需要几分钟)…");
      const documentId = await pollSummaryUntilDone(submitted.video_id);
      message.success("总结完成！");
      navigate(`/youtube/summary/${documentId}`);
    } catch (e) {
      const msg = String(e);
      if (msg.includes("no_transcript") || msg.includes("没有字幕")) {
        message.error("该视频没有字幕,且语音识别不可用,无法总结。");
      } else {
        message.error("总结失败：" + msg);
      }
    } finally {
      setSummarizing(false);
    }
  }

  return (
    <main className="page dashboard-page">
      <PageHeader
        title="仪表盘"
        description="你的 YouTube 订阅总结概览 —— 统计数据与最近总结均来自真实后端。"
      />

      {error && (
        <Alert
          type="error"
          message="加载数据失败"
          description={`${error}（请确认后端服务正在运行）`}
          style={{ marginBottom: 16 }}
        />
      )}

      <Card style={{ marginBottom: 16 }}>
        <Space.Compact style={{ width: "100%" }}>
          <Input
            size="large"
            placeholder="粘贴 YouTube 视频链接，立即总结..."
            value={summaryUrl}
            onChange={(e) => setSummaryUrl(e.target.value)}
            onPressEnter={handleSummarize}
            prefix={<LinkOutlined />}
          />
          <Button
            type="primary"
            size="large"
            icon={<ThunderboltOutlined />}
            loading={summarizing}
            onClick={handleSummarize}
          >
            总结视频
          </Button>
        </Space.Compact>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Card loading={loading}>
            <Statistic
              title="已启用订阅"
              value={stats.subscriptions}
              prefix={<YoutubeOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={loading}>
            <Statistic
              title="已总结视频"
              value={stats.summarized_videos}
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={loading}>
            <Statistic
              title="抽取实体"
              value={stats.entities}
              prefix={<NodeIndexOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={loading}>
            <Statistic title="实体关系" value={stats.relations} prefix={<NodeIndexOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} className="section-row">
        <Col xs={24} xl={16}>
          <Card
            title="最近总结"
            className="panel-card"
            extra={<Link to="/youtube">查看全部</Link>}
          >
            <Spin spinning={loading}>
              {summaries.length === 0 && !loading ? (
                <Empty description="还没有总结过的视频。去 YouTube 页面粘贴一个链接试试。" />
              ) : (
                <List
                  dataSource={summaries}
                  renderItem={(item) => (
                    <List.Item key={item.document_id}>
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
                          <Space size={6}>
                            {item.is_unread && (
                              <StarFilled style={{ color: "#faad14", fontSize: 13 }} />
                            )}
                            <Link to={`/youtube/summary/${item.document_id}`}>
                              {item.title}
                            </Link>
                          </Space>
                        }
                        description={
                          <Space direction="vertical" size={0} style={{ width: "100%" }}>
                            {item.channel_name && (
                              <Text type="secondary">{item.channel_name}</Text>
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
                      {item.duration_sec && (
                        <Text type="secondary">
                          <ClockCircleOutlined /> {Math.floor(item.duration_sec / 60)}分钟
                        </Text>
                      )}
                    </List.Item>
                  )}
                />
              )}
            </Spin>
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="快速操作" className="panel-card">
            <Space direction="vertical" style={{ width: "100%" }} size="middle">
              <Link to="/youtube">
                <Card size="small" hoverable>
                  <Space>
                    <ThunderboltOutlined style={{ fontSize: 20, color: "#1677ff" }} />
                    <span>
                      <div style={{ fontWeight: 500 }}>手动总结视频</div>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        粘贴 YouTube 链接，立即获取带时间戳的总结
                      </Text>
                    </span>
                  </Space>
                </Card>
              </Link>
              <Link to="/youtube/subscriptions">
                <Card size="small" hoverable>
                  <Space>
                    <YoutubeOutlined style={{ fontSize: 20, color: "#52c41a" }} />
                    <span>
                      <div style={{ fontWeight: 500 }}>管理订阅</div>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        添加频道，自动总结最新更新
                      </Text>
                    </span>
                  </Space>
                </Card>
              </Link>
              <Link to="/graph">
                <Card size="small" hoverable>
                  <Space>
                    <NodeIndexOutlined style={{ fontSize: 20, color: "#722ed1" }} />
                    <span>
                      <div style={{ fontWeight: 500 }}>探索知识图谱</div>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        查看跨视频抽取的实体与关系
                      </Text>
                    </span>
                  </Space>
                </Card>
              </Link>
            </Space>
          </Card>
        </Col>
      </Row>
    </main>
  );
}
