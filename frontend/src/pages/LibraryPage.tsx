import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Card,
  Col,
  Empty,
  Input,
  List,
  Row,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";

import { PageHeader } from "../components/PageHeader";
import { documentApi, type DocumentSummary } from "../services/documentApi";

const { Text, Paragraph } = Typography;

const STATUS_COLOR: Record<string, string> = {
  completed: "success",
  pending: "default",
  running: "processing",
  failed: "error",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function LibraryPage() {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<DocumentSummary | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await documentApi.list();
      setDocs(result);
      if (result.length > 0 && !selected) setSelected(result[0]);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = filter.trim()
    ? docs.filter((d) => d.title.toLowerCase().includes(filter.toLowerCase()))
    : docs;

  return (
    <main className="page">
      <PageHeader
        title="文档库"
        description="浏览已导入的文档及其解析、抽取状态。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card
            title={`文档 (${docs.length})`}
            className="panel-card"
            extra={
              <Input
                size="small"
                placeholder="筛选..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                style={{ width: 140 }}
              />
            }
            styles={{ body: { maxHeight: 560, overflow: "auto" } }}
          >
            {error && <Alert type="error" message={error} style={{ marginBottom: 8 }} />}
            {loading ? (
              <Skeleton active />
            ) : visible.length === 0 ? (
              <Empty description="暂无文档" />
            ) : (
              <List
                size="small"
                dataSource={visible}
                renderItem={(doc) => (
                  <List.Item
                    style={{
                      cursor: "pointer",
                      padding: "6px 8px",
                      borderRadius: 4,
                      background: selected?.id === doc.id ? "#e6f4ff" : "transparent",
                    }}
                    onClick={() => setSelected(doc)}
                  >
                    <List.Item.Meta
                      title={
                        <Text strong={selected?.id === doc.id} style={{ fontSize: 13 }}>
                          {doc.title}
                        </Text>
                      }
                      description={
                        <Space size={4} wrap>
                          <Tag>{doc.source_type}</Tag>
                          <Tag color={STATUS_COLOR[doc.parse_status] ?? "default"}>
                            {doc.parse_status}
                          </Tag>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="文档详情" className="panel-card">
            {!selected ? (
              <Empty description="选择左侧文档查看详情" />
            ) : (
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <div>
                  <Text type="secondary">标题</Text>
                  <Paragraph style={{ margin: 0 }}>
                    <Text strong style={{ fontSize: 16 }}>
                      {selected.title}
                    </Text>
                  </Paragraph>
                </div>
                <Row gutter={16}>
                  <Col span={12}>
                    <Text type="secondary">来源类型</Text>
                    <div>
                      <Tag color="blue">{selected.source_type}</Tag>
                    </div>
                  </Col>
                  <Col span={12}>
                    <Text type="secondary">内容类型</Text>
                    <div>
                      <Tag>{selected.content_type ?? "未知"}</Tag>
                    </div>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={8}>
                    <Text type="secondary">解析状态</Text>
                    <div>
                      <Tag color={STATUS_COLOR[selected.parse_status] ?? "default"}>
                        {selected.parse_status}
                      </Tag>
                    </div>
                  </Col>
                  <Col span={8}>
                    <Text type="secondary">索引状态</Text>
                    <div>
                      <Tag color={STATUS_COLOR[selected.status] ?? "default"}>
                        {selected.status}
                      </Tag>
                    </div>
                  </Col>
                  <Col span={8}>
                    <Text type="secondary">更新时间</Text>
                    <div>
                      <Text>{fmtDate(selected.updated_at)}</Text>
                    </div>
                  </Col>
                </Row>
              </Space>
            )}
          </Card>
        </Col>
      </Row>
    </main>
  );
}
