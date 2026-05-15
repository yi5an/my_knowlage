import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  FileSearchOutlined,
  ReadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { Button, Card, Col, List, Progress, Row, Space, Statistic, Tag, Typography } from "antd";
import { Link } from "react-router-dom";

import { PageHeader } from "../components/PageHeader";
import { actionItems, recentActivities, workspaceStats } from "../mockData";

const quickStarts = [
  { title: "Import sources", icon: <CloudUploadOutlined />, to: "/import" },
  { title: "Ask the library", icon: <SearchOutlined />, to: "/search" },
  { title: "Open reader", icon: <ReadOutlined />, to: "/reader" },
  { title: "Start research", icon: <FileSearchOutlined />, to: "/research" },
];

export function DashboardPage() {
  return (
    <main className="page dashboard-page">
      <PageHeader
        title="Dashboard"
        description="A lightweight workspace for resuming work, handling review queues, and jumping into focused tools."
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={8}>
          <Card title="Continue last work" className="panel-card">
            <Typography.Title level={4}>AI Agent local knowledge base PRD</Typography.Title>
            <Typography.Paragraph type="secondary">
              Last edited section: entity extraction and industry-chain modeling.
            </Typography.Paragraph>
            <Progress percent={74} showInfo={false} />
            <Button type="primary" icon={<ArrowRightOutlined />}>
              Continue
            </Button>
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="Needs attention" className="panel-card">
            <List
              dataSource={actionItems}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    avatar={<CheckCircleOutlined className="attention-icon" />}
                    title={item.title}
                    description={item.detail}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="Quick start" className="panel-card">
            <div className="quick-grid">
              {quickStarts.map((item) => (
                <Link className="quick-action" to={item.to} key={item.to}>
                  {item.icon}
                  <span>{item.title}</span>
                </Link>
              ))}
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} className="section-row">
        <Col xs={24} xl={14}>
          <Card title="Recent activity" className="panel-card">
            <List
              dataSource={recentActivities}
              renderItem={(activity) => (
                <List.Item>
                  <Typography.Text>{activity}</Typography.Text>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title="Knowledge base status" className="panel-card">
            <Row gutter={[12, 12]}>
              {workspaceStats.map((stat) => (
                <Col span={12} key={stat.label}>
                  <Statistic title={stat.label} value={stat.value} />
                  <Tag color={stat.tone}>tracked</Tag>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
      </Row>

      <Card title="Feature map" className="panel-card section-row">
        <Space wrap>
          {["Import", "Library", "Reader", "Graph", "Search", "Research", "NotebookLM"].map(
            (feature) => (
              <Tag className="feature-tag" key={feature}>
                {feature}
              </Tag>
            ),
          )}
        </Space>
      </Card>
    </main>
  );
}
