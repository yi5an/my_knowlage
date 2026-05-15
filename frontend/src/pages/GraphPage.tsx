import { Card, Col, Row, Space, Tag, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";
import { graphNodes } from "../mockData";

export function GraphPage() {
  return (
    <main className="page">
      <PageHeader
        title="Knowledge graph"
        description="Static mock graph for UI validation; graph sync and algorithms belong to later backend work."
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={5}>
          <Card title="Filters" className="panel-card">
            <Space wrap>
              <Tag color="blue">Technology</Tag>
              <Tag color="gold">Stock</Tag>
              <Tag color="purple">Industry chain</Tag>
              <Tag color="green">Evidence</Tag>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={13}>
          <div className="graph-canvas" aria-label="Mock knowledge graph">
            <div className="graph-edge edge-a" />
            <div className="graph-edge edge-b" />
            <div className="graph-edge edge-c" />
            {graphNodes.map((node) => (
              <div
                key={node.id}
                className={`graph-node ${node.className}`}
                style={{ left: `${node.x}%`, top: `${node.y}%` }}
              >
                {node.label}
              </div>
            ))}
          </div>
        </Col>
        <Col xs={24} lg={6}>
          <Card title="Node detail" className="panel-card">
            <Typography.Title level={4}>NVIDIA</Typography.Title>
            <Typography.Paragraph>
              Connected to GPU demand, TSMC manufacturing, and cloud AI workloads.
            </Typography.Paragraph>
            <Tag color="blue">5 evidence snippets</Tag>
          </Card>
        </Col>
      </Row>
    </main>
  );
}

