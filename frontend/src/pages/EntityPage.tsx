import { Card, Col, Descriptions, List, Row, Space, Tag, Timeline, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";

export function EntityPage() {
  return (
    <main className="page">
      <PageHeader
        title="实体详情"
        description="实体档案、别名、关系与证据预览，使用静态演示数据。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card className="panel-card">
            <Typography.Title level={3}>NVIDIA</Typography.Title>
            <Space wrap>
              <Tag color="blue">股票</Tag>
              <Tag color="green">已验证</Tag>
              <Tag>NVDA</Tag>
            </Space>
            <Descriptions column={1} className="description-list">
              <Descriptions.Item label="交易所">NASDAQ</Descriptions.Item>
              <Descriptions.Item label="行业">半导体</Descriptions.Item>
              <Descriptions.Item label="工作区">AI 投资研究</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="关系与证据" className="panel-card">
            <Timeline
              items={[
                { children: "台积电提供先进制造产能。" },
                { children: "GPU 需求由云端 AI 工作负载驱动。" },
                { children: "出口管制作为风险因素进行追踪。" },
              ]}
            />
          </Card>
        </Col>
      </Row>
      <Card title="提及" className="panel-card section-row">
        <List
          dataSource={["AI 算力供应链研究", "半导体产业图谱"]}
          renderItem={(item) => <List.Item>{item}</List.Item>}
        />
      </Card>
    </main>
  );
}

