import { Card, Col, List, Row, Space, Tag, Tree, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";
import { documents } from "../mockData";

export function LibraryPage() {
  return (
    <main className="page">
      <PageHeader
        title="文档库"
        description="按分类浏览文档，无需重复阅读或导入流程。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={6}>
          <Card title="分类" className="panel-card">
            <Tree
              defaultExpandAll
              treeData={[
                {
                  title: "技术",
                  key: "tech",
                  children: [{ title: "AI 智能体", key: "agents" }],
                },
                {
                  title: "投资",
                  key: "investment",
                  children: [{ title: "AI 算力", key: "compute" }],
                },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="文档" className="panel-card">
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
          <Card title="AI 预览" className="panel-card">
            <Typography.Paragraph>
              选择文档以预览摘要、标签和抽取状态。
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

