import { BulbOutlined, CommentOutlined, TagsOutlined } from "@ant-design/icons";
import { Button, Card, Col, List, Row, Space, Tag, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";

export function ReaderPage() {
  return (
    <main className="page reader-page">
      <PageHeader
        title="Reader"
        description="Three-column reading, outline, document body, and AI notes panel."
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={5}>
          <Card title="Outline" className="panel-card sticky-panel">
            <List
              size="small"
              dataSource={["Overview", "Architecture", "AI pipeline", "Evidence model"]}
              renderItem={(item) => <List.Item>{item}</List.Item>}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <article className="reader-document">
            <Typography.Title level={2}>AI Agent local knowledge base</Typography.Title>
            <Typography.Paragraph>
              KnowPilot combines local document storage, structured extraction, hybrid search, and
              knowledge graph navigation.
            </Typography.Paragraph>
            <Typography.Paragraph>
              <mark>GraphRAG connects document chunks with verified entities and relations.</mark>
              Each AI-generated answer must keep evidence and confidence fields.
            </Typography.Paragraph>
            <Typography.Paragraph>
              The reader reserves space for annotations, citations, and assistant workflows without
              triggering backend business logic.
            </Typography.Paragraph>
          </article>
        </Col>
        <Col xs={24} lg={7}>
          <Card title="Assistant and notes" className="panel-card sticky-panel">
            <Space wrap>
              <Button icon={<BulbOutlined />}>Explain</Button>
              <Button icon={<TagsOutlined />}>Extract</Button>
              <Button icon={<CommentOutlined />}>Note</Button>
            </Space>
            <div className="note-box">
              <Tag color="gold">Pending</Tag>
              <Typography.Text>Review relation: GraphRAG improves multi-hop retrieval.</Typography.Text>
            </div>
          </Card>
        </Col>
      </Row>
    </main>
  );
}

