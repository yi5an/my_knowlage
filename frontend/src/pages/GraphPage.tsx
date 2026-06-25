import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  Row,
  Segmented,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { SearchOutlined } from "@ant-design/icons";

import { PageHeader } from "../components/PageHeader";
import { GraphCanvas, NodeTypeLegend, type ContextAction, type LayoutKind } from "../components/GraphCanvas";
import { EntityNodeList } from "../components/EntityNodeList";
import {
  graphApi,
  type GraphEdge,
  type GraphNode,
  type GraphResponse,
} from "../services/graphApi";

const { Title, Paragraph, Text } = Typography;

export function GraphPage() {
  const [query, setQuery] = useState("");
  const [data, setData] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [expanding, setExpanding] = useState(false);
  const [layout, setLayout] = useState<LayoutKind>("force");
  // "entities" hides document/chunk/entity_type nodes so the graph shows the
  // knowledge graph (entities + their relations), not raw content nodes.
  const [viewScope, setViewScope] = useState<"entities" | "all">("entities");
  const [nodeFilter, setNodeFilter] = useState("");

  const search = useCallback(
    async (q: string) => {
      setLoading(true);
      setError(null);
      setSelected(null);
      try {
        // In "entities" scope, ask the backend to only return entity nodes —
        // otherwise the default limit is filled with document/chunk nodes and
        // entities get cut off entirely.
        const nodeTypes = viewScope === "entities" ? ["entity"] : undefined;
        const result = q.trim()
          ? await graphApi.search(q.trim(), "ws_default", 50, nodeTypes)
          : await graphApi.search("*", "ws_default", 50, nodeTypes);
        setData(result);
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    },
    [viewScope],
  );

  useEffect(() => {
    search("*");
  }, [search]);

  async function expandNode(node: GraphNode) {
    setSelected(node);
    if (node.node_type !== "entity") return;
    setExpanding(true);
    try {
      const neighbors = await graphApi.neighbors(node.id, 2, 50);
      setData((prev) => {
        if (!prev) return neighbors;
        const mergedNodes = [...prev.nodes, ...neighbors.nodes].filter(
          (n, i, arr) => arr.findIndex((x) => x.id === n.id) === i,
        );
        const mergedEdges = [...prev.edges, ...neighbors.edges].filter(
          (e, i, arr) => arr.findIndex((x) => x.id === e.id) === i,
        );
        return { nodes: mergedNodes, edges: mergedEdges };
      });
    } catch {
      // ignore expansion errors
    } finally {
      setExpanding(false);
    }
  }

  // Backend already filtered by node_types, so visibleData == data.
  const visibleData = data;
  const incidentEdges: GraphEdge[] = visibleData
    ? visibleData.edges.filter(
        (e) => selected && (e.source_id === selected.id || e.target_id === selected.id),
      )
    : [];

  return (
    <main className="page">
      <PageHeader
        title="知识图谱"
        description="从所有已总结视频中抽取的实体与关系。点击节点可展开其邻域。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={5}>
          <Card
            title="实体列表"
            className="panel-card"
            styles={{ body: { maxHeight: 560, overflow: "auto" } }}
          >
            <EntityNodeList
              nodes={visibleData?.nodes ?? []}
              selectedId={selected?.id}
              filter={nodeFilter}
              onFilterChange={setNodeFilter}
              onSelect={(n) => {
                setSelected(n);
              }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={13}>
          <Card
            className="panel-card"
            styles={{ body: { height: 520, padding: 0 } }}
            title={
              <Space wrap>
                <Text strong>图谱</Text>
                {visibleData && (
                  <Tag color="blue">
                    {visibleData.nodes.length} 个节点 · {visibleData.edges.length} 条边
                  </Tag>
                )}
                {expanding && <Spin size="small" />}
                <NodeTypeLegend />
                <Input
                  size="small"
                  placeholder="搜索实体..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onPressEnter={() => search(query)}
                  prefix={<SearchOutlined />}
                  style={{ width: 140 }}
                />
                <Segmented
                  size="small"
                  value={viewScope}
                  onChange={(v) => setViewScope(v as "entities" | "all")}
                  options={[
                    { label: "仅实体", value: "entities" },
                    { label: "全部", value: "all" },
                  ]}
                />
                <Segmented
                  size="small"
                  value={layout}
                  onChange={(v) => setLayout(v as LayoutKind)}
                  options={[
                    { label: "力导向", value: "force" },
                    { label: "同心圆", value: "radial" },
                    { label: "网格", value: "grid" },
                  ]}
                />
              </Space>
            }
          >
            {error && <Alert type="error" message={error} style={{ margin: 8 }} />}
            {loading ? (
              <div style={{ display: "flex", justifyContent: "center", paddingTop: 200 }}>
                <Spin size="large" />
              </div>
            ) : visibleData && visibleData.nodes.length > 0 ? (
              <GraphCanvas
                nodes={visibleData.nodes}
                edges={visibleData.edges}
                selectedId={selected?.id}
                layout={layout}
                onSelectNode={expandNode}
                onContextAction={(action, node) => {
                  switch (action) {
                    case "detail":
                      setSelected(node);
                      break;
                    case "expand":
                      void expandNode(node);
                      break;
                    case "copy":
                      void navigator.clipboard?.writeText(node.label);
                      break;
                    case "search":
                      setQuery(node.label);
                      void search(node.label);
                      break;
                  }
                }}
              />
            ) : (
              <div style={{ paddingTop: 160 }}>
                <Empty description="暂无实体。总结视频后将自动填充图谱。" />
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={6}>
          <Card title="节点详情" className="panel-card">
            {selected ? (
              <Space direction="vertical" size="small" style={{ width: "100%" }}>
                <Title level={4} style={{ marginBottom: 4 }}>
                  {selected.label}
                </Title>
                <Tag color="purple">{selected.node_type}</Tag>
                <Paragraph style={{ marginTop: 8 }}>
                  <Text type="secondary">连接数：</Text>
                  <Text strong>{incidentEdges.length}</Text>
                </Paragraph>
                {incidentEdges.length > 0 && (
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      关系：
                    </Text>
                    <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
                      {incidentEdges.slice(0, 8).map((e) => {
                        const otherId = e.source_id === selected.id ? e.target_id : e.source_id;
                        const other = data?.nodes.find((n) => n.id === otherId);
                        return (
                          <li key={e.id} style={{ fontSize: 12 }}>
                            <Tag>{e.relation_type}</Tag>
                            {other?.label ?? otherId}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </Space>
            ) : (
              <Text type="secondary">选择一个节点查看其详情与关系。</Text>
            )}
          </Card>
        </Col>
      </Row>
    </main>
  );
}
