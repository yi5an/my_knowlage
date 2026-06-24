import { BulbOutlined, CommentOutlined, TagsOutlined } from "@ant-design/icons";
import { Button, Card, Col, List, Row, Space, Tag, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";

export function ReaderPage() {
  return (
    <main className="page reader-page">
      <PageHeader
        title="阅读"
        description="三栏阅读：大纲、正文与 AI 笔记面板。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={5}>
          <Card title="大纲" className="panel-card sticky-panel">
            <List
              size="small"
              dataSource={["概览", "架构", "AI 流水线", "证据模型"]}
              renderItem={(item) => <List.Item>{item}</List.Item>}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <article className="reader-document">
            <Typography.Title level={2}>AI Agent 本地知识库</Typography.Title>
            <Typography.Paragraph>
              KnowPilot 结合本地文档存储、结构化抽取、混合检索与知识图谱导航。
            </Typography.Paragraph>
            <Typography.Paragraph>
              <mark>GraphRAG 将文档块与已验证的实体和关系连接起来。</mark>
              每个 AI 生成的回答都必须保留证据与置信度字段。
            </Typography.Paragraph>
            <Typography.Paragraph>
              阅读器为批注、引用与助手工作流预留空间，且不会触发后端业务逻辑。
            </Typography.Paragraph>
          </article>
        </Col>
        <Col xs={24} lg={7}>
          <Card title="助手与笔记" className="panel-card sticky-panel">
            <Space wrap>
              <Button icon={<BulbOutlined />}>解释</Button>
              <Button icon={<TagsOutlined />}>抽取</Button>
              <Button icon={<CommentOutlined />}>笔记</Button>
            </Space>
            <div className="note-box">
              <Tag color="gold">待处理</Tag>
              <Typography.Text>审阅关系：GraphRAG 提升多跳检索能力。</Typography.Text>
            </div>
          </Card>
        </Col>
      </Row>
    </main>
  );
}

