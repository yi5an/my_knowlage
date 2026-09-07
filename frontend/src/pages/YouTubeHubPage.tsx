import { useState } from "react";
import { Link } from "react-router-dom";
import { Button, Card, Col, Input, List, message, Row, Space, Spin, Tag, Typography } from "antd";
import { LinkOutlined, ThunderboltOutlined, YoutubeOutlined } from "@ant-design/icons";

import { summarizeVideo } from "../services/youtubeApi";
import { YouTubeTimeline } from "../components/youtube/YouTubeTimeline";

const { Title, Text, Paragraph } = Typography;

export function YouTubeHubPage() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);

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
      window.dispatchEvent(new Event("youtube-timeline-refresh"));
    } catch (e) {
      const msg = String(e);
      if (msg.includes("no_transcript") || msg.includes("没有字幕")) {
        message.error("该视频没有字幕，且语音识别不可用，无法总结。");
      } else {
        message.error("总结失败：" + msg);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <div>
          <Title level={2} style={{ marginBottom: 4 }}>
            <YoutubeOutlined /> YouTube 视频总结
          </Title>
          <Text type="secondary">粘贴任意 YouTube 链接，立即获取带时间戳的视频总结。</Text>
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
              onChange={(event) => setUrl(event.target.value)}
              onPressEnter={handleSummarize}
              prefix={<LinkOutlined />}
            />
            <Button type="primary" size="large" loading={busy} onClick={handleSummarize}>
              总结
            </Button>
          </Space.Compact>
          {busy && (
            <div style={{ marginTop: 16 }}>
              <Spin tip="正在后台处理：获取字幕/语音识别 → 翻译 → 总结 → 抽取实体…" />
            </div>
          )}
        </Card>

        <Card title="历史总结" extra={<Link to="/youtube/subscriptions">订阅管理</Link>}>
          <YouTubeTimeline />
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
