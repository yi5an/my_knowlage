import { useCallback, useEffect, useState } from "react";
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
  Typography,
} from "antd";

import { PageHeader } from "../components/PageHeader";
import { researchApi, type ResearchTask } from "../services/researchApi";

const { Paragraph, Text, Title } = Typography;

const STATUS_COLOR: Record<string, string> = {
  running: "processing",
  completed: "success",
  imported: "blue",
  failed: "error",
};

function reportOf(task: ResearchTask): Record<string, unknown> | null {
  const report = task.metadata?.report;
  return report && typeof report === "object" ? (report as Record<string, unknown>) : null;
}

export function ResearchPage() {
  const [tasks, setTasks] = useState<ResearchTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

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

  const selected = tasks.find((t) => t.id === selectedId) ?? null;
  const report = selected ? reportOf(selected) : null;

  return (
    <main className="page">
      <PageHeader
        title="深度研究"
        description="输入研究问题，Agent 自动检索、交叉验证并生成结构化报告。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={7}>
          <Card title="新建研究" className="panel-card" style={{ marginBottom: 16 }}>
            <Space.Compact style={{ width: "100%" }}>
              <Input
                placeholder="研究问题，例如：AI 基建产业链有哪些关键环节"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onPressEnter={createTask}
              />
              <Button type="primary" loading={creating} onClick={createTask}>
                开始研究
              </Button>
            </Space.Compact>
          </Card>
          <Card title={`任务 (${tasks.length})`} className="panel-card">
            {loading ? (
              <Spin />
            ) : (
              <List
                dataSource={tasks}
                locale={{ emptyText: <Empty description="还没有研究任务" /> }}
                renderItem={(task) => (
                  <List.Item onClick={() => setSelectedId(task.id)} style={{ cursor: "pointer" }}>
                    <List.Item.Meta
                      title={task.title}
                      description={
                        <Space size={4}>
                          <Tag color={STATUS_COLOR[task.status] ?? "default"}>{task.status}</Tag>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {task.question.slice(0, 30)}
                          </Text>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={17}>
          {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
          {!selected ? (
            <Card className="panel-card">
              <Empty description="选择一个任务查看报告，或新建一个研究。" />
            </Card>
          ) : (
            <Card
              className="panel-card"
              title={
                <Space>
                  <Title level={4} style={{ margin: 0 }}>
                    {selected.title}
                  </Title>
                  <Tag color={STATUS_COLOR[selected.status] ?? "default"}>{selected.status}</Tag>
                </Space>
              }
            >
              {report ? (
                <ResearchReportView report={report} />
              ) : selected.status === "failed" ? (
                <Alert
                  type="error"
                  message="研究失败"
                  description={String(
                    (selected.metadata?.error as Record<string, unknown>)?.message ?? "未知错误",
                  )}
                />
              ) : (
                <Empty description={selected.status === "running" ? "研究进行中…" : "暂无报告"} />
              )}
            </Card>
          )}
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
