import { type ReactNode, useEffect, useState } from "react";
import { BulbOutlined, CheckOutlined, CloseOutlined, SafetyOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Empty, List, Row, Space, Spin, Tag, Typography } from "antd";
import { useParams } from "react-router-dom";

import { PageHeader } from "../components/PageHeader";
import { useOptionalCompanion } from "../components/companion/companionContext";
import { readingCompanionApi } from "../services/readingCompanionApi";
import type { ReadingInsight, ReaderDocument } from "../types/readingCompanion";

const KIND_LABEL = { understanding: "理解", impact: "主题影响", risk: "风险" };
const EVIDENCE_LABEL = { corroborated: "多源佐证", conflicted: "存在冲突", insufficient: "本地资料不足" };

export function ReaderPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const companion = useOptionalCompanion();
  const setCompanionContext = companion?.setContext;
  const clearCompanionContext = companion?.clearContext;
  const [reader, setReader] = useState<ReaderDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(documentId));
  const companionDocumentId = reader?.document_id;
  const companionWorkspaceId = reader?.workspace_id;
  const companionTitle = reader?.title;

  useEffect(() => {
    if (!documentId) return;
    let cancelled = false;
    readingCompanionApi.getReader(documentId).then((value) => {
      if (!cancelled) setReader(value);
    }).catch((reason) => {
      if (!cancelled) setError(String(reason));
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [documentId]);

  useEffect(() => {
    if (!documentId || !reader || reader.analysis) return;
    let cancelled = false;
    readingCompanionApi.trigger(documentId).then((job) => readingCompanionApi.getAnalysis(job.analysis_id)).then((analysis) => {
      if (!cancelled) setReader((current) => current ? { ...current, analysis } : current);
    }).catch((reason) => {
      if (!cancelled) setError(String(reason));
    });
    return () => { cancelled = true; };
  }, [documentId, reader]);

  useEffect(() => {
    if (!companionDocumentId || !companionWorkspaceId || !companionTitle || !setCompanionContext) return;
    setCompanionContext({
      workspaceId: companionWorkspaceId,
      subjectType: "document",
      subjectId: companionDocumentId,
      title: companionTitle,
    });
    return () => clearCompanionContext?.(companionDocumentId);
  }, [
    clearCompanionContext,
    companionDocumentId,
    companionTitle,
    companionWorkspaceId,
    setCompanionContext,
  ]);

  const analysisId = reader?.analysis?.id;
  const analysisStatus = reader?.analysis?.status;
  useEffect(() => {
    if (!analysisId || !analysisStatus || !["pending", "running"].includes(analysisStatus)) return;
    const timer = window.setInterval(() => {
      readingCompanionApi.getAnalysis(analysisId).then((fresh) => {
        setReader((current) => current ? { ...current, analysis: fresh } : current);
      }).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [analysisId, analysisStatus]);

  async function startAnalysis() {
    if (!documentId) return;
    const job = await readingCompanionApi.trigger(documentId);
    const analysis = await readingCompanionApi.getAnalysis(job.analysis_id);
    setReader((current) => current ? { ...current, analysis } : current);
  }

  async function review(insight: ReadingInsight, status: "confirmed" | "dismissed") {
    await readingCompanionApi.updateInsight(insight.id, status);
    if (!reader?.analysis) return;
    setReader({
      ...reader,
      analysis: {
        ...reader.analysis,
        insights: reader.analysis.insights.map((item) => item.id === insight.id ? { ...item, status } : item),
      },
    });
  }

  if (!documentId) return <ReaderPicker />;
  if (loading) return <main className="page"><Spin tip="正在加载阅读材料..." /></main>;
  if (error || !reader) return <main className="page"><Alert type="error" message={error ?? "文档不存在"} /></main>;

  const insights = reader.analysis?.insights.filter((item) => item.status !== "dismissed") ?? [];
  return (
    <main className="page reader-page">
      <PageHeader title={reader.title} description="AI 主动标记重点，并用本地资料提供佐证或冲突信息。" />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={5}><Card title="大纲" className="panel-card sticky-panel"><List size="small" dataSource={reader.chunks} renderItem={(item) => <List.Item><a href={`#chunk-${item.id}`}>{item.heading ?? "正文"}</a></List.Item>} /></Card></Col>
        <Col xs={24} lg={12}><article className="reader-document">{reader.chunks.map((chunk) => <section id={`chunk-${chunk.id}`} key={chunk.id}><Typography.Title level={3}>{chunk.heading}</Typography.Title><Typography.Paragraph>{renderChunk(chunk.content, insights.filter((item) => item.chunk_id === chunk.id))}</Typography.Paragraph></section>)}</article></Col>
        <Col xs={24} lg={7}><Card title="AI 陪读" className="panel-card sticky-panel" extra={<BulbOutlined />}>
          {!reader.analysis && <Button type="primary" onClick={() => void startAnalysis()}>开始分析</Button>}
          {reader.analysis && ["pending", "running"].includes(reader.analysis.status) && <Spin tip="正在分析文档与本地证据..." />}
          {reader.analysis?.status === "failed" && <Alert type="error" message={reader.analysis.error_message ?? "分析失败"} action={<Button size="small" onClick={() => void startAnalysis()}>重试</Button>} />}
          {reader.analysis?.status === "completed" && <InsightList insights={insights} onReview={review} />}
        </Card></Col>
      </Row>
    </main>
  );
}

function ReaderPicker() {
  return <main className="page"><PageHeader title="阅读" description="选择文档后，AI 会主动解释重点、影响和风险。" /><Empty description="请从文档库打开一篇文档开始陪读。" /></main>;
}

function InsightList({ insights, onReview }: { insights: ReadingInsight[]; onReview: (insight: ReadingInsight, status: "confirmed" | "dismissed") => Promise<void> }) {
  if (!insights.length) return <Empty description="尚未发现需要标记的内容。" />;
  return <List dataSource={insights} renderItem={(insight) => <List.Item><Card size="small" style={{ width: "100%" }} title={<Space><Tag color={insight.kind === "risk" ? "error" : "processing"}>{KIND_LABEL[insight.kind]}</Tag>{insight.headline}</Space>}>
    <Typography.Paragraph>{insight.explanation}</Typography.Paragraph><Typography.Text type="secondary">{insight.why_it_matters}</Typography.Text>
    <div style={{ marginTop: 8 }}><Tag icon={<SafetyOutlined />} color={insight.evidence_state === "conflicted" ? "warning" : "default"}>{EVIDENCE_LABEL[insight.evidence_state]}</Tag></div>
    {insight.corroborations.map((source) => <Typography.Paragraph key={source.id} style={{ marginTop: 8 }}><Tag>{source.stance}</Tag><b>{source.source_title}</b>：{source.excerpt}</Typography.Paragraph>)}
    {insight.status === "active" && <Space><Button size="small" icon={<CheckOutlined />} onClick={() => void onReview(insight, "confirmed")}>确认</Button><Button size="small" icon={<CloseOutlined />} onClick={() => void onReview(insight, "dismissed")}>忽略</Button></Space>}
  </Card></List.Item>} />;
}

function renderChunk(content: string, insights: ReadingInsight[]) {
  const anchors = insights
    .filter((item) => item.start_offset >= 0 && item.end_offset <= content.length)
    .sort((left, right) => left.start_offset - right.start_offset);
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const insight of anchors) {
    if (insight.start_offset < cursor) continue;
    nodes.push(content.slice(cursor, insight.start_offset));
    nodes.push(<mark key={insight.id} title={`${KIND_LABEL[insight.kind]}：${insight.headline}`}>{content.slice(insight.start_offset, insight.end_offset)}</mark>);
    cursor = insight.end_offset;
  }
  nodes.push(content.slice(cursor));
  return nodes;
}
