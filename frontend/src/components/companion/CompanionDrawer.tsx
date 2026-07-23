import { useEffect, useState } from "react";
import { BulbOutlined, SendOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Drawer, Empty, Input, List, Space, Tag, Typography } from "antd";

import { companionApi } from "../../services/companionApi";
import type { CompanionMessage, CompanionSessionDetail, CompanionSubjectType } from "../../types/companion";
import { useCompanion } from "./companionContext";

const SUBJECT_LABEL: Record<CompanionSubjectType, string> = {
  document: "文档",
  youtube_video: "视频",
  information_edge: "信息差",
  workspace: "工作区",
};

export function CompanionDrawer() {
  const { activeContext, close, isOpen, open } = useCompanion();
  const [detail, setDetail] = useState<CompanionSessionDetail | null>(null);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !activeContext) return;
    let cancelled = false;
    setError(null);
    setDetail(null);
    void companionApi.createOrReuseSession(activeContext)
      .then(async (session) => {
        const current = await companionApi.getSession(session.id);
        if (!cancelled) {
          setDetail(current);
          void companionApi.triggerInsights(session.id);
        }
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => { cancelled = true; };
  }, [activeContext, isOpen]);

  async function send() {
    if (!detail || !question.trim() || sending) return;
    const content = question.trim();
    setQuestion("");
    setSending(true);
    const userMessage: CompanionMessage = {
      id: `pending-${Date.now()}`,
      role: "user",
      content,
      citations: [],
      confidence: null,
    };
    setDetail((current) => current ? { ...current, messages: [...current.messages, userMessage] } : current);
    try {
      const reply = await companionApi.sendMessage(detail.id, content);
      setDetail((current) => current ? { ...current, messages: [...current.messages, reply] } : current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <Button
        aria-label="AI 陪读"
        type="primary"
        shape="round"
        icon={<BulbOutlined />}
        onClick={open}
        style={{ position: "fixed", right: 28, bottom: 28, zIndex: 1000 }}
      >
        AI 陪读
      </Button>
      <Drawer title="AI 陪读" open={isOpen} onClose={close} width={440} destroyOnClose={false}>
        {!activeContext ? (
          <Empty description="打开文档、视频或信息差信号后即可开始陪读。" />
        ) : (
          <Space direction="vertical" size="middle" style={{ width: "100%" }}>
            <Tag color="blue">{SUBJECT_LABEL[activeContext.subjectType]}：{activeContext.title}</Tag>
            {error && <Alert type="error" message={error} />}
            {detail?.insights.length ? (
              <section>
                <Typography.Title level={5}>主动提示</Typography.Title>
                <List
                  size="small"
                  dataSource={detail.insights}
                  renderItem={(insight) => <List.Item><Card size="small" title={insight.headline}>{insight.content}</Card></List.Item>}
                />
              </section>
            ) : null}
            <List
              size="small"
              dataSource={detail?.messages ?? []}
              locale={{ emptyText: "可询问证据、风险、机会或反证。" }}
              renderItem={(message) => <List.Item><Space direction="vertical" size={4} style={{ width: "100%" }}>
                <Typography.Text strong={message.role === "user"}>{message.role === "user" ? "你" : "AI 陪读"}</Typography.Text>
                <Typography.Paragraph style={{ marginBottom: 0 }}>{message.content}</Typography.Paragraph>
                {message.citations.map((citation) => <Typography.Text key={citation.source_id} type="secondary">
                  {citation.relation === "corroborates" ? "平台内佐证" : "原始证据"} · {citation.source_title} · {Math.round(citation.confidence * 100)}%
                </Typography.Text>)}
              </Space></List.Item>}
            />
            <Input.Search
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onSearch={() => void send()}
              placeholder="围绕当前内容提问…"
              enterButton={<Button aria-label="发送" type="primary" icon={<SendOutlined />}>发送</Button>}
              loading={sending}
              disabled={!detail}
            />
          </Space>
        )}
      </Drawer>
    </>
  );
}
