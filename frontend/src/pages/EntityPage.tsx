import { Card, Col, Descriptions, List, Row, Space, Tag, Timeline, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";

export function EntityPage() {
  return (
    <main className="page">
      <PageHeader
        title="Entity detail"
        description="Entity profile, aliases, relations, and evidence preview using static mock data."
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card className="panel-card">
            <Typography.Title level={3}>NVIDIA</Typography.Title>
            <Space wrap>
              <Tag color="blue">Stock</Tag>
              <Tag color="green">Verified</Tag>
              <Tag>NVDA</Tag>
            </Space>
            <Descriptions column={1} className="description-list">
              <Descriptions.Item label="Exchange">NASDAQ</Descriptions.Item>
              <Descriptions.Item label="Industry">Semiconductors</Descriptions.Item>
              <Descriptions.Item label="Workspace">AI investment research</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="Relations and evidence" className="panel-card">
            <Timeline
              items={[
                { children: "TSMC supplies advanced manufacturing capacity." },
                { children: "GPU demand is driven by cloud AI workloads." },
                { children: "Export controls are tracked as a risk factor." },
              ]}
            />
          </Card>
        </Col>
      </Row>
      <Card title="Mentions" className="panel-card section-row">
        <List
          dataSource={["AI compute supply chain research", "Semiconductor industry map"]}
          renderItem={(item) => <List.Item>{item}</List.Item>}
        />
      </Card>
    </main>
  );
}

