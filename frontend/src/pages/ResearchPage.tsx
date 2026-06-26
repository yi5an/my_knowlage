import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  List,
  Row,
  Space,
  Spin,
  Steps,
  Tag,
  Tooltip,
  Typography,
} from "antd";

import { PageHeader } from "../components/PageHeader";
import { entityApi, type EntitySummary } from "../services/entityApi";
import { researchApi, type ResearchTask } from "../services/researchApi";

const { Paragraph, Text, Title } = Typography;

const STATUS_COLOR: Record<string, string> = {
  running: "processing",
  completed: "success",
  imported: "blue",
  failed: "error",
};

const STATUS_LABEL: Record<string, string> = {
  running: "研究中",
  completed: "待导入",
  imported: "已入库",
  failed: "失败",
};

function reportOf(task: ResearchTask): Record<string, unknown> | null {
  const report = task.metadata?.report;
  return report && typeof report === "object" ? (report as Record<string, unknown>) : null;
}

function friendlyError(msg: string): string {
  if (msg.includes("structured output")) return "AI 模型返回格式异常，多次重试后仍失败。可稍后重试。";
  if (msg.includes("web search is not configured") || msg.includes("TAVILY_API_KEY"))
    return "未配置网络搜索(Tavily)，请在 .env 设置 TAVILY_API_KEY。";
  if (msg.includes("Interrupted") || msg.includes("中断")) return "服务重启，任务被中断。可重新运行。";
  return msg;
}

export function ResearchPage() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<ResearchTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [entities, setEntities] = useState<EntitySummary[]>([]);
  const [entitiesLoading, setEntitiesLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await researchApi.list();
      setTasks(result);
      if (result.length > 0 && selectedId === null) {
        setSelectedId(result[0].id);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll while any task is still running: the workflow takes 2-3 minutes and
  // we want the list/report to update as soon as it finishes.
  const hasRunning = tasks.some((t) => t.status === "running");
  useEffect(() => {
    if (!hasRunning) return;
    const timer = setInterval(async () => {
      try {
        const fresh = await researchApi.list();
        setTasks(fresh);
      } catch {
        // ignore transient poll errors
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [hasRunning]);

  async function createTask() {
    if (!question.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const task = await researchApi.create(question.trim());
      setTasks((prev) => [task, ...prev]);
      setSelectedId(task.id);
      setQuestion("");
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(false);
    }
  }

  async function importTask() {
    if (!selected) return;
    setImporting(true);
    setError(null);
    try {
      await researchApi.importReport(selected.id);
      // After import, the worker extracts entities asynchronously. Poll the
      // task list until it flips to "imported", then refresh.
      const poll = setInterval(async () => {
        const fresh = await researchApi.list();
        const updated = fresh.find((t) => t.id === selected.id);
        setTasks(fresh);
        if (updated && updated.status === "imported") {
          clearInterval(poll);
          setImporting(false);
        }
      }, 3000);
    } catch (e) {
      setError(String(e));
      setImporting(false);
    }
  }

  // Load entities when the selected task is imported (entities extracted).
  const selected = tasks.find((t) => t.id === selectedId) ?? null;
  const report = selected ? reportOf(selected) : null;
  const canImport = selected?.status === "completed";
  const showEntities = selected?.status === "imported";

  useEffect(() => {
    if (!selected || selected.status !== "imported") {
      setEntities([]);
      return;
    }
    let cancelled = false;
    setEntitiesLoading(true);
    entityApi
      .list(selected.workspace_id)
      .then((list) => {
        if (!cancelled) setEntities(list);
      })
      .catch(() => {
        if (!cancelled) setEntities([]);
      })
      .finally(() => {
        if (!cancelled) setEntitiesLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id, selected?.status]);

  return (
    <main className="page">
      <PageHeader
        title="深度研究"
        description="输入研究问题，Agent 自动检索、交叉验证并生成结构化报告；导入后可查看提取的实体与图谱。"
      />
      <Row gutter={[16, 16]}>
        {/* 左:历史研究列表 */}
        <Col xs={24} lg={6}>
          <Card title="历史研究" className="panel-card" style={{ marginBottom: 16 }}>
            <Space.Compact style={{ width: "100%", marginBottom: 12 }}>
              <Input
                placeholder="研究问题..."
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onPressEnter={createTask}
              />
              <Button type="primary" loading={creating} onClick={createTask}>
                开始研究
              </Button>
            </Space.Compact>
            {loading ? (
              <Spin />
            ) : (
              <List
                dataSource={tasks}
                locale={{ emptyText: <Empty description="还没有研究任务" /> }}
                renderItem={(task) => (
                  <List.Item
                    onClick={() => setSelectedId(task.id)}
                    style={{
                      cursor: "pointer",
                      padding: "6px 8px",
                      borderRadius: 4,
                      background: selected?.id === task.id ? "#e6f4ff" : "transparent",
                    }}
                  >
                    <List.Item.Meta
                      title={
                        <Space size={4}>
                          <Text strong={selected?.id === task.id} style={{ fontSize: 13 }}>
                            {task.title.length > 14 ? task.title.slice(0, 13) + "…" : task.title}
                          </Text>
                          <Tag
                            color={STATUS_COLOR[task.status] ?? "default"}
                            icon={task.status === "running" ? <Spin size="small" /> : undefined}
                            style={{ marginInlineEnd: 0 }}
                          >
                            {STATUS_LABEL[task.status] ?? task.status}
                          </Tag>
                        </Space>
                      }
                      description={
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {task.question.slice(0, 24)}
                        </Text>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        {/* 中:报告 + 导入按钮 */}
        <Col xs={24} lg={11}>
          {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
          {!selected ? (
            <Card className="panel-card">
              <Empty description="选择一个任务查看报告，或新建一个研究。" />
            </Card>
          ) : (
            <Card
              className="panel-card"
              title={
                <Space wrap>
                  <Title level={4} style={{ margin: 0 }}>
                    {selected.title}
                  </Title>
                  <Tag color={STATUS_COLOR[selected.status] ?? "default"}>
                    {STATUS_LABEL[selected.status] ?? selected.status}
                  </Tag>
                  {selected.status === "running" && <Spin size="small" />}
                </Space>
              }
              extra={
                canImport && (
                  <Button type="primary" loading={importing} onClick={importTask}>
                    导入知识库
                  </Button>
                )
              }
            >
              {report ? (
                <ResearchReportView report={report} />
              ) : selected.status === "failed" ? (
                <Alert
                  type="error"
                  message="研究失败"
                  description={friendlyError(
                    String(
                      (selected.metadata?.error as Record<string, unknown>)?.message ??
                        "未知错误",
                    ),
                  )}
                />
              ) : (
                <Empty description={selected.status === "running" ? "研究进行中…" : "暂无报告"} />
              )}
            </Card>
          )}
        </Col>

        {/* 右:实体 + 图谱入口 */}
        <Col xs={24} lg={7}>
          <Card
            title="提取的实体"
            className="panel-card"
            extra={
              showEntities && (
                <Tooltip title="在图谱中查看">
                  <Button
                    size="small"
                    type="link"
                    onClick={() => navigate("/graph")}
                  >
                    查看图谱 →
                  </Button>
                </Tooltip>
              )
            }
          >
            {!showEntities ? (
              <Empty
                description={
                  canImport
                    ? "导入知识库后将自动提取实体"
                    : selected?.status === "imported"
                      ? "正在提取实体…"
                      : "完成研究并导入后显示"
                }
              />
            ) : entitiesLoading ? (
              <Spin />
            ) : entities.length === 0 ? (
              <Empty description="暂无实体" />
            ) : (
              <List
                size="small"
                dataSource={entities.slice(0, 20)}
                locale={{ emptyText: "暂无实体" }}
                renderItem={(entity) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <Space size={4}>
                          <Text style={{ fontSize: 13 }}>
                            {entity.properties?.zh_name ?? entity.name}
                          </Text>
                          <Tag style={{ marginInlineEnd: 0 }}>{entity.entity_type_id}</Tag>
                        </Space>
                      }
                      description={
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {entity.name}
                        </Text>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
            {showEntities && entities.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <Button block onClick={() => navigate("/graph")}>
                  打开知识图谱
                </Button>
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </main>
  );
}

function ResearchReportView({ report }: { report: Record<string, unknown> }) {
  const summary = String(report.summary ?? "");
  const background = String(report.background ?? "");
  const findings = (report.key_findings as string[]) ?? [];
  const steps = (report.next_steps as string[]) ?? [];

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      {summary && (
        <div>
          <Text strong>摘要</Text>
          <Paragraph>{summary}</Paragraph>
        </div>
      )}
      {background && (
        <div>
          <Text strong>背景</Text>
          <Paragraph>{background}</Paragraph>
        </div>
      )}
      {findings.length > 0 && (
        <div>
          <Text strong>关键发现</Text>
          <ul style={{ margin: "8px 0", paddingLeft: 20 }}>
            {findings.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}
      {steps.length > 0 && (
        <div>
          <Text strong>下一步建议</Text>
          <Steps
            direction="vertical"
            size="small"
            current={steps.length}
            items={steps.map((s) => ({ title: s }))}
          />
        </div>
      )}
    </Space>
  );
}
