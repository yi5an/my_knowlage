import { Card, Col, List, Row, Space, Tag, Tree, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";
import { documents } from "../mockData";

export function LibraryPage() {
  return (
    <main className="page">
      <PageHeader
        title="Library"
        description="Browse categorized documents without duplicating reader or import workflows."
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={6}>
          <Card title="Categories" className="panel-card">
            <Tree
              defaultExpandAll
              treeData={[
                {
                  title: "Technology",
                  key: "tech",
                  children: [{ title: "AI Agents", key: "agents" }],
                },
                {
                  title: "Investment",
                  key: "investment",
                  children: [{ title: "AI Compute", key: "compute" }],
                },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Documents" className="panel-card">
            <List
              dataSource={documents}
              renderItem={(doc) => (
                <List.Item>
                  <List.Item.Meta
                    title={doc.title}
                    description={
                      <Space wrap>
                        <Tag>{doc.type}</Tag>
                        <Tag color="blue">{doc.status}</Tag>
                        <Typography.Text type="secondary">{doc.updatedAt}</Typography.Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={6}>
          <Card title="AI preview" className="panel-card">
            <Typography.Paragraph>
              Select a document to preview summaries, tags, and extraction status.
            </Typography.Paragraph>
            <Space wrap>
              <Tag color="blue">RAG</Tag>
              <Tag color="purple">GraphRAG</Tag>
              <Tag color="gold">Qdrant</Tag>
            </Space>
          </Card>
        </Col>
      </Row>
    </main>
  );
}

