import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Alert,
  Empty,
  Input,
  List,
  Row,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  SaveOutlined,
  UndoOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  YoutubeOutlined,
} from "@ant-design/icons";

import {
  getSummaryCard,
  importSummaryToKnowledgeBase,
  markSummaryRead,
  updateVisualFrameMindmap,
  youtubeThumbnailUrl,
  youtubeTimestampUrl,
  type VideoFrameAnalysis,
  type SourceTraceCandidate,
  type VisualMindmapTreeNode,
  type VideoSummaryCard,
} from "../services/youtubeApi";
import { investmentApi } from "../services/investmentApi";
import { MindmapView } from "../components/MindmapView";

const { Title, Paragraph, Text } = Typography;

export function VideoSummaryPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const [card, setCard] = useState<VideoSummaryCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [creatingClaim, setCreatingClaim] = useState(false);
  const [importingToKnowledgeBase, setImportingToKnowledgeBase] = useState(false);
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

  const handleCreateClaim = async () => {
    setCreatingClaim(true);
    try {
      await investmentApi.createClaim({
        claim_text: summary.tldr,
        required_evidence: summary.key_points.map((p) => p.point),
      });
      message.success("已提取为待验证观点");
    } catch (e) {
      message.error(e instanceof Error ? e.message : String(e));
    } finally {
      setCreatingClaim(false);
    }
  };

  const handleImportToKnowledgeBase = async () => {
    setImportingToKnowledgeBase(true);
    try {
      const updated = await importSummaryToKnowledgeBase(card.document_id);
      setCard(updated);
      message.success("已加入知识库");
    } catch (e) {
      message.error(e instanceof Error ? e.message : String(e));
    } finally {
      setImportingToKnowledgeBase(false);
    }
  };

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
            {card.thumbnail_url && youtubeThumbnailUrl(card.video_id) && (
              <Col>
                <img
                  src={youtubeThumbnailUrl(card.video_id) ?? undefined}
                  alt=""
                  style={{ width: 160, height: 90, borderRadius: 8, objectFit: "cover" }}
                  onError={(event) => {
                    event.currentTarget.style.display = "none";
                  }}
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
                {card.knowledge_base_imported ? (
                  <Tag icon={<CheckCircleOutlined />} color="success">
                    已加入知识库
                  </Tag>
                ) : (
                  <Button
                    type="primary"
                    icon={<DatabaseOutlined />}
                    loading={importingToKnowledgeBase}
                    onClick={() => void handleImportToKnowledgeBase()}
                  >
                    加入知识库
                  </Button>
                )}
                <Button loading={creatingClaim} onClick={() => void handleCreateClaim()}>
                  提取为待验证观点
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

        {card.source_traces?.length > 0 && (
          <Card title="可能信息来源">
            <List
              dataSource={card.source_traces}
              renderItem={(trace) => <SourceTraceItem trace={trace} />}
            />
          </Card>
        )}

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
              key: "visual",
              label: "视觉资料",
              children: card.visual_frames?.length ? (
                <VisualEvidenceList frames={card.visual_frames} videoId={card.video_id} />
              ) : (
                <Empty description="暂无视觉资料" />
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

function SourceTraceItem({ trace }: { trace: SourceTraceCandidate }) {
  return (
    <List.Item>
      <List.Item.Meta
        title={
          <Space wrap>
            <Text strong>{trace.source_title}</Text>
            {trace.source_name && <Tag>{trace.source_name}</Tag>}
            {trace.lead_time_hours !== null && (
              <Tag color="blue">领先 {formatLeadHours(trace.lead_time_hours)}</Tag>
            )}
            <Tag>置信度 {Math.round(trace.confidence * 100)}%</Tag>
          </Space>
        }
        description={
          <Space direction="vertical" size={2}>
            <span>匹配事实：{trace.matched_fact}</span>
            <span>证据：{trace.evidence_excerpt}</span>
            {trace.source_url && (
              <a href={trace.source_url} target="_blank" rel="noreferrer">
                打开原始来源
              </a>
            )}
          </Space>
        }
      />
    </List.Item>
  );
}

function formatLeadHours(value: number): string {
  if (Number.isInteger(value)) {
    return `${value}h`;
  }
  return `${value.toFixed(1)}h`;
}

const frameTypeLabel: Record<VideoFrameAnalysis["frame_type"], string> = {
  slide: "PPT",
  mindmap: "脑图",
  chart: "图表",
  table: "表格",
  screen_text: "屏幕文字",
  other: "其他",
};

interface VisualMindmapLayoutNode {
  id: string;
  parentId: string | null;
  title: string;
  level: number;
  color: string;
  x: number;
  y: number;
  width: number;
  height: number;
  isLeaf: boolean;
  isRoot: boolean;
}

const visualMindmapColors = [
  "#1677ff",
  "#52c41a",
  "#fa8c16",
  "#eb2f96",
  "#722ed1",
  "#13c2c2",
];

function cleanVisualNoteLines(lines: string[], title: string): string[] {
  const seen = new Set<string>();
  return lines
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .filter((line) => line !== title.trim())
    .filter((line) => !/^[<>{}()[\]|/\\•·\-—_]+$/.test(line))
    .filter((line) => {
      if (seen.has(line)) return false;
      seen.add(line);
      return true;
    });
}

function isVisualSectionHeading(line: string): boolean {
  if (line.length > 28) return false;
  if (/[。！？!?]/.test(line)) return false;
  if (/[-—]/.test(line)) return true;
  if (/(背景|驱动|催化|成果|结论|演变|预判|逻辑|观点|优势|主线|影响|分析)$/.test(line)) {
    return true;
  }
  return false;
}

function splitVisualHeading(line: string): { heading: string; detail: string } | null {
  const match = /^([^：:]{2,14})[：:](.+)$/.exec(line);
  if (!match) return null;
  return { heading: match[1].trim(), detail: match[2].trim() };
}

function buildVisualMindmapNodes(lines: string[]): VisualMindmapTreeNode[] {
  const nodes: VisualMindmapTreeNode[] = [];
  let current: VisualMindmapTreeNode | null = null;

  const ensureOverview = () => {
    const existing = nodes.find((node) => node.title === "核心摘要");
    if (existing) {
      current = existing;
      return existing;
    }
    current = { title: "核心摘要", children: [] };
    nodes.push(current);
    return current;
  };

  for (const line of lines) {
    const split = splitVisualHeading(line);
    if (split) {
      current = {
        title: split.heading,
        children: split.detail ? [{ title: split.detail, children: [] }] : [],
      };
      nodes.push(current);
      continue;
    }
    if (isVisualSectionHeading(line)) {
      current = { title: line, children: [] };
      nodes.push(current);
      continue;
    }
    if (current) {
      current.children.push({ title: line, children: [] });
    } else {
      ensureOverview().children.push({ title: line, children: [] });
    }
  }

  return nodes.filter((node) => node.title !== "核心摘要" || node.children.length > 0);
}

function VisualEvidenceList({
  frames,
  videoId,
}: {
  frames: VideoFrameAnalysis[];
  videoId: string;
}) {
  return (
    <List
      dataSource={frames}
      renderItem={(frame) => <VisualFrameItem frame={frame} videoId={videoId} />}
    />
  );
}

function VisualFrameItem({
  frame,
  videoId,
}: {
  frame: VideoFrameAnalysis;
  videoId: string;
}) {
  const [showRawOcr, setShowRawOcr] = useState(false);
  const [savedTree, setSavedTree] = useState<VisualMindmapTreeNode | null>(() =>
    normalizeVisualMindmapTree(frame.structured_notes?.tree),
  );

  useEffect(() => {
    setSavedTree(normalizeVisualMindmapTree(frame.structured_notes?.tree));
  }, [frame.id, frame.structured_notes?.tree]);

  const title =
    savedTree?.title ||
    (typeof frame.structured_notes?.title === "string"
      ? frame.structured_notes.title.trim()
      : "");
  const rawBullets = Array.isArray(frame.structured_notes?.bullets)
    ? frame.structured_notes.bullets.filter((item): item is string => typeof item === "string")
    : [];
  const bullets = cleanVisualNoteLines(rawBullets, title);
  const shouldShowRawToggle = Boolean(frame.ocr_text.trim());
  const shouldRenderMindmap =
    (savedTree !== null || bullets.length > 0) &&
    (frame.frame_type === "mindmap" || frame.frame_type === "table");

  const handleSaveMindmap = async (tree: VisualMindmapTreeNode) => {
    if (!frame.id) throw new Error("当前视觉帧缺少 ID，无法保存脑图。");
    const updated = await updateVisualFrameMindmap(frame.id, tree);
    const updatedTree = normalizeVisualMindmapTree(updated.structured_notes?.tree);
    setSavedTree(updatedTree ?? tree);
  };

  return (
    <List.Item>
      <Space align="start" size="middle" style={{ width: "100%" }}>
        {frame.image_url && (
          <a
            href={frame.image_url}
            target="_blank"
            rel="noreferrer"
            aria-label="打开视觉资料图片"
            title="打开视觉资料图片"
            style={{ display: "inline-flex" }}
          >
            <img
              src={frame.image_url}
              alt={title || frame.frame_type}
              style={{
                width: 180,
                borderRadius: 6,
                border: "1px solid #eee",
                cursor: "zoom-in",
              }}
            />
          </a>
        )}
        <Space direction="vertical" size={6} style={{ width: "100%" }}>
          <Space wrap>
            <Tag color="purple">{frameTypeLabel[frame.frame_type]}</Tag>
            <TimestampLink
              videoId={videoId}
              ts={frame.timestamp_sec}
              label={frame.timestamp_str}
              monospace
            />
            <Text type="secondary">置信度 {Math.round(frame.confidence * 100)}%</Text>
          </Space>
          {title && <Text strong>{title}</Text>}
          {shouldRenderMindmap ? (
            <VisualOcrMindmap
              rootTitle={title || frameTypeLabel[frame.frame_type]}
              lines={bullets}
              tree={savedTree}
              canEdit={Boolean(frame.id)}
              onSave={handleSaveMindmap}
            />
          ) : bullets.length > 0 ? (
            <ul style={{ margin: "2px 0 0", paddingLeft: 18, lineHeight: 1.8 }}>
              {bullets.map((item) => (
                <li key={item}>
                  <Text>{item}</Text>
                </li>
              ))}
            </ul>
          ) : null}
          {shouldShowRawToggle && (
            <Button
              type="link"
              size="small"
              style={{ alignSelf: "flex-start", padding: 0 }}
              onClick={() => setShowRawOcr((current) => !current)}
            >
              {showRawOcr ? "收起原始 OCR" : "展开查看原始 OCR"}
            </Button>
          )}
          {showRawOcr && (
            <Paragraph
              type="secondary"
              style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}
            >
              {frame.ocr_text}
            </Paragraph>
          )}
        </Space>
      </Space>
    </List.Item>
  );
}

function VisualOcrMindmap({
  rootTitle,
  lines,
  tree,
  canEdit,
  onSave,
}: {
  rootTitle: string;
  lines: string[];
  tree: VisualMindmapTreeNode | null;
  canEdit: boolean;
  onSave: (tree: VisualMindmapTreeNode) => Promise<void>;
}) {
  const sourceNode = useMemo(
    () => tree ?? { title: rootTitle, children: buildVisualMindmapNodes(lines) },
    [lines, rootTitle, tree],
  );
  const sourceKey = JSON.stringify(sourceNode);
  const [draftTree, setDraftTree] = useState<VisualMindmapTreeNode>(() =>
    cloneVisualMindmapTree(sourceNode),
  );
  const [isEditing, setIsEditing] = useState(false);
  const [selectedPath, setSelectedPath] = useState("root");
  const [saving, setSaving] = useState(false);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    setDraftTree(cloneVisualMindmapTree(sourceNode));
    setSelectedPath("root");
    setIsEditing(false);
  }, [sourceKey, sourceNode]);

  const rootNode = isEditing ? draftTree : sourceNode;
  if (rootNode.children.length === 0) return null;

  const leafGap = 16;
  const branchGap = 24;
  const topPadding = 56;
  const columnGap = 82;
  const rootWidth = 210;
  const rootHeight = 76;
  const getLevelWidth = (level: number) => {
    if (level === 0) return rootWidth;
    if (level === 1) return 230;
    if (level === 2) return 230;
    return 360;
  };
  const getLevelLeft = (level: number) => {
    let left = rootWidth + 108;
    for (let current = 1; current < level; current += 1) {
      left += getLevelWidth(current) + columnGap;
    }
    return left;
  };
  const estimateNodeHeight = (title: string, width: number) => {
    const weightedLength = Array.from(title).reduce(
      (total, char) => total + (char.charCodeAt(0) > 255 ? 1 : 0.55),
      0,
    );
    const charsPerLine = Math.max(8, Math.floor(width / 14));
    return Math.max(34, Math.ceil(weightedLength / charsPerLine) * 19 + 14);
  };
  let nextY = topPadding;

  const layoutNodes: VisualMindmapLayoutNode[] = [];
  const visit = (
    node: VisualMindmapTreeNode,
    level: number,
    parentId: string | null,
    branchColor: string,
    indexPath: number[],
  ): number => {
    const id = indexPath.join("-");
    const childYs = node.children.map((child, index) =>
      visit(
        child,
        level + 1,
        id,
        branchColor,
        [...indexPath, index],
      ),
    );
    const y = childYs.length
      ? childYs.reduce((sum, childY) => sum + childY, 0) / childYs.length
      : nextY;
    const width = getLevelWidth(level);
    const height = estimateNodeHeight(node.title, width);
    if (!childYs.length) {
      nextY += height + leafGap;
    } else {
      nextY += branchGap;
    }
    layoutNodes.push({
      id,
      parentId,
      title: node.title,
      level,
      color: branchColor,
      x: getLevelLeft(level),
      y,
      width,
      height,
      isLeaf: node.children.length === 0,
      isRoot: false,
    });
    return y;
  };

  rootNode.children.forEach((node, index) => {
    visit(node, 1, null, visualMindmapColors[index % visualMindmapColors.length], [index]);
    nextY += branchGap;
  });

  const maxLevel = Math.max(...layoutNodes.map((node) => node.level), 1);
  const canvasWidth = Math.max(1160, getLevelLeft(maxLevel) + getLevelWidth(maxLevel) + 80);
  const canvasHeight = Math.max(220, nextY + topPadding);
  const rootY = layoutNodes[0]?.y ?? canvasHeight / 2;
  const rootLayoutNode: VisualMindmapLayoutNode = {
    id: "root",
    parentId: null,
    title: rootNode.title || rootTitle,
    level: 0,
    color: "#1677ff",
    x: 24,
    y: rootY,
    width: rootWidth,
    height: rootHeight,
    isLeaf: false,
    isRoot: true,
  };
  const allNodes = [rootLayoutNode, ...layoutNodes];
  const nodesById = new Map(allNodes.map((node) => [node.id, node]));
  const edges = allNodes
    .filter((node) => node.id !== "root")
    .map((node) => ({ child: node, parent: nodesById.get(node.parentId ?? "root") ?? rootLayoutNode }))
    .filter((edge): edge is { child: VisualMindmapLayoutNode; parent: VisualMindmapLayoutNode } =>
      Boolean(edge.parent),
    );
  const selectedNode = getVisualMindmapNode(rootNode, selectedPath);

  const updateTitle = (path: string, title: string) => {
    setDraftTree((current) => updateVisualMindmapTitle(current, path, title));
  };

  const addChild = () => {
    const result = addVisualMindmapChild(draftTree, selectedPath);
    setDraftTree(result.tree);
    setSelectedPath(result.path);
  };

  const deleteSelected = () => {
    if (selectedPath === "root") return;
    const result = deleteVisualMindmapNode(draftTree, selectedPath);
    setDraftTree(result.tree);
    setSelectedPath(result.path);
  };

  const save = async () => {
    setSaving(true);
    try {
      await onSave(draftTree);
      message.success("脑图已保存");
      setIsEditing(false);
    } catch (e) {
      message.error(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      role="tree"
      aria-label="视觉资料脑图"
      style={{
        width: "100%",
        border: "1px solid #e6efff",
        borderRadius: 8,
        background: "linear-gradient(180deg, #fbfdff 0%, #ffffff 64%)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.8)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          padding: "10px 12px",
          borderBottom: "1px solid #edf2ff",
        }}
      >
        <Space wrap size={6}>
          <Tag color="blue">可编辑脑图</Tag>
          {isEditing && selectedNode && (
            <Text type="secondary">已选中：{selectedNode.title || "未命名节点"}</Text>
          )}
        </Space>
        <Space wrap size={6}>
          {isEditing && (
            <>
              <Button size="small" icon={<PlusOutlined />} onClick={addChild}>
                新增子节点
              </Button>
              <Button
                size="small"
                icon={<DeleteOutlined />}
                disabled={selectedPath === "root"}
                onClick={deleteSelected}
              >
                删除节点
              </Button>
              <Button
                size="small"
                icon={<UndoOutlined />}
                onClick={() => {
                  setDraftTree(cloneVisualMindmapTree(sourceNode));
                  setSelectedPath("root");
                }}
              >
                重置
              </Button>
            </>
          )}
          <Button
            size="small"
            icon={<ZoomOutOutlined />}
            onClick={() => setScale((current) => Math.max(0.75, Number((current - 0.1).toFixed(2))))}
            aria-label="缩小脑图"
          />
          <Button
            size="small"
            icon={<ZoomInOutlined />}
            onClick={() => setScale((current) => Math.min(1.3, Number((current + 0.1).toFixed(2))))}
            aria-label="放大脑图"
          />
          {isEditing ? (
            <Button
              type="primary"
              size="small"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={() => void save()}
            >
              保存脑图
            </Button>
          ) : (
            <Button
              size="small"
              icon={<EditOutlined />}
              disabled={!canEdit}
              onClick={() => {
                setDraftTree(cloneVisualMindmapTree(rootNode));
                setSelectedPath("root");
                setIsEditing(true);
              }}
            >
              编辑脑图
            </Button>
          )}
        </Space>
      </div>
      <div
        style={{
          overflow: "auto",
          padding: "16px 0 18px",
        }}
      >
        <div
          data-testid="visual-mindmap-canvas"
          style={{
            position: "relative",
            width: canvasWidth,
            height: canvasHeight,
            fontSize: 13,
            lineHeight: "18px",
            transform: `scale(${scale})`,
            transformOrigin: "top left",
          }}
        >
          <svg
            data-testid="visual-mindmap-branches"
            aria-hidden="true"
            width={canvasWidth}
            height={canvasHeight}
            style={{
              position: "absolute",
              inset: 0,
              overflow: "visible",
            }}
          >
            <defs>
              {visualMindmapColors.map((color, index) => (
                <marker
                  key={color}
                  id={`visual-mindmap-dot-${index}`}
                  markerWidth="6"
                  markerHeight="6"
                  refX="3"
                  refY="3"
                >
                  <circle cx="3" cy="3" r="2.4" fill="#fff" stroke={color} strokeWidth="1.2" />
                </marker>
              ))}
            </defs>
            {edges.map(({ child, parent }) => {
              const startX = parent.x + parent.width;
              const childRootIndex = Number(child.id.split("-")[0] ?? 0);
              const rootChildCount = Math.max(rootNode.children.length, 1);
              const startY = parent.isRoot
                ? parent.y + (childRootIndex - (rootChildCount - 1) / 2) * 16
                : parent.y;
              const endX = child.x;
              const colorIndex = visualMindmapColors.indexOf(child.color);
              return (
                <path
                  key={`edge-${parent.id}-${child.id}`}
                  data-testid="visual-mindmap-curve"
                  d={`M ${startX} ${startY} C ${startX + 54} ${startY}, ${endX - 68} ${child.y}, ${endX} ${child.y}`}
                  fill="none"
                  stroke={child.color}
                  strokeWidth={child.level <= 1 ? 2.2 : 1.45}
                  strokeLinecap="round"
                  markerEnd={`url(#visual-mindmap-dot-${Math.max(colorIndex, 0)})`}
                />
              );
            })}
            {allNodes.map((item) => (
              <circle
                key={`dot-${item.id}`}
                data-testid="visual-mindmap-dot"
                cx={item.x + item.width}
                cy={item.y}
                r={item.isRoot ? 4.2 : 3}
                fill="#fff"
                stroke={item.color}
                strokeWidth={1.4}
              />
            ))}
          </svg>
          {allNodes.map((item) => {
            const selected = isEditing && selectedPath === item.id;
            const nodePath = item.id;
            return (
              <div
                key={`node-${item.id}`}
                data-testid={item.isRoot ? "visual-mindmap-root" : "visual-mindmap-node"}
                role="treeitem"
                aria-level={item.level + 1}
                onClick={() => isEditing && setSelectedPath(nodePath)}
                onKeyDown={(event) => {
                  if (isEditing && (event.key === "Enter" || event.key === " ")) {
                    event.preventDefault();
                    setSelectedPath(nodePath);
                  }
                }}
                tabIndex={isEditing ? 0 : -1}
                style={{
                  position: "absolute",
                  left: item.x,
                  top: item.y - item.height / 2,
                  width: item.width,
                  minHeight: item.height,
                  border: selected ? `2px solid ${item.color}` : "1px solid rgba(22, 119, 255, 0.18)",
                  borderRadius: item.isRoot ? 18 : 999,
                  padding: item.isRoot ? "13px 18px" : "8px 14px",
                  color: item.isRoot ? "#fff" : "#1f1f1f",
                  background: item.isRoot
                    ? "linear-gradient(135deg, #1677ff 0%, #13c2c2 100%)"
                    : item.isLeaf
                      ? "#fff"
                      : `linear-gradient(180deg, ${item.color}18 0%, #fff 100%)`,
                  boxShadow: selected
                    ? `0 0 0 4px ${item.color}22, 0 12px 28px rgba(15, 35, 70, 0.14)`
                    : "0 8px 22px rgba(15, 35, 70, 0.08)",
                  font: "inherit",
                  fontWeight: item.isRoot ? 700 : item.level === 1 ? 650 : 500,
                  textAlign: "left",
                  whiteSpace: "normal",
                  overflowWrap: "anywhere",
                  wordBreak: "break-word",
                  cursor: isEditing ? "text" : "default",
                }}
              >
                {isEditing ? (
                  <Input.TextArea
                    aria-label={item.isRoot ? "编辑根节点" : `编辑节点 ${item.title}`}
                    value={item.title}
                    rows={Math.max(1, Math.min(4, Math.round(item.height / 20)))}
                    variant="borderless"
                    onClick={(event) => {
                      event.stopPropagation();
                      setSelectedPath(nodePath);
                    }}
                    onFocus={() => setSelectedPath(nodePath)}
                    onChange={(event) => updateTitle(nodePath, event.target.value)}
                    style={{
                      padding: 0,
                      color: item.isRoot ? "#fff" : "#1f1f1f",
                      fontWeight: "inherit",
                      lineHeight: "18px",
                      background: "transparent",
                      resize: "none",
                    }}
                  />
                ) : item.isLeaf ? (
                  <span data-testid="visual-mindmap-leaf">{item.title}</span>
                ) : (
                  item.title
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function cloneVisualMindmapTree(node: VisualMindmapTreeNode): VisualMindmapTreeNode {
  return {
    title: node.title,
    children: node.children.map(cloneVisualMindmapTree),
  };
}

function visualPathToIndexes(path: string): number[] {
  if (path === "root" || path.length === 0) return [];
  return path.split("-").map((part) => Number(part));
}

function getVisualMindmapNode(
  root: VisualMindmapTreeNode,
  path: string,
): VisualMindmapTreeNode | null {
  let node = root;
  for (const index of visualPathToIndexes(path)) {
    const next = node.children[index];
    if (!next) return null;
    node = next;
  }
  return node;
}

function updateVisualMindmapTitle(
  root: VisualMindmapTreeNode,
  path: string,
  title: string,
): VisualMindmapTreeNode {
  if (path === "root") {
    return { ...root, title };
  }
  const indexes = visualPathToIndexes(path);
  const update = (node: VisualMindmapTreeNode, depth: number): VisualMindmapTreeNode => {
    if (depth === indexes.length) {
      return { ...node, title };
    }
    return {
      ...node,
      children: node.children.map((child, index) =>
        index === indexes[depth] ? update(child, depth + 1) : child,
      ),
    };
  };
  return update(root, 0);
}

function addVisualMindmapChild(
  root: VisualMindmapTreeNode,
  path: string,
): { tree: VisualMindmapTreeNode; path: string } {
  const indexes = visualPathToIndexes(path);
  let newPath = "";
  const add = (node: VisualMindmapTreeNode, depth: number): VisualMindmapTreeNode => {
    if (depth === indexes.length) {
      const childIndex = node.children.length;
      newPath = [...indexes, childIndex].join("-");
      return {
        ...node,
        children: [...node.children, { title: "新节点", children: [] }],
      };
    }
    return {
      ...node,
      children: node.children.map((child, index) =>
        index === indexes[depth] ? add(child, depth + 1) : child,
      ),
    };
  };
  return { tree: add(root, 0), path: newPath };
}

function deleteVisualMindmapNode(
  root: VisualMindmapTreeNode,
  path: string,
): { tree: VisualMindmapTreeNode; path: string } {
  const indexes = visualPathToIndexes(path);
  const parentPath = indexes.slice(0, -1).join("-") || "root";
  const removeIndex = indexes[indexes.length - 1];
  const remove = (node: VisualMindmapTreeNode, depth: number): VisualMindmapTreeNode => {
    if (depth === indexes.length - 1) {
      return {
        ...node,
        children: node.children.filter((_, index) => index !== removeIndex),
      };
    }
    return {
      ...node,
      children: node.children.map((child, index) =>
        index === indexes[depth] ? remove(child, depth + 1) : child,
      ),
    };
  };
  return { tree: remove(root, 0), path: parentPath };
}

function normalizeVisualMindmapTree(raw: unknown): VisualMindmapTreeNode | null {
  if (!raw || typeof raw !== "object") return null;
  const maybeNode = raw as { title?: unknown; children?: unknown };
  if (typeof maybeNode.title !== "string" || !Array.isArray(maybeNode.children)) {
    return null;
  }
  return {
    title: maybeNode.title,
    children: maybeNode.children
      .map(normalizeVisualMindmapTree)
      .filter((node): node is VisualMindmapTreeNode => node !== null),
  };
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
