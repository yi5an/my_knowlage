import { Card, Col, List, Progress, Row, Steps, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";
import { researchTasks } from "../mockData";

export function ResearchPage() {
  return (
    <main className="page">
      <PageHeader
        title="Deep research"
        description="Task list, report draft, and agent process are separated from document import and search pages."
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={7}>
          <Card title="Tasks" className="panel-card">
            <List
              dataSource={researchTasks}
              renderItem={(task) => (
                <List.Item>
                  <List.Item.Meta title={task.title} description={task.status} />
                  <Progress type="circle" percent={task.progress} size={44} />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="Report draft" className="panel-card">
            <Typography.Title level={4}>AI compute supply chain</Typography.Title>
            <Typography.Paragraph>
              Early evidence suggests advanced lithography, wafer fabrication, GPU design, and cloud
              demand are the main dependency layers.
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={24} lg={7}>
          <Card title="Agent process" className="panel-card">
            <Steps
              direction="vertical"
              size="small"
              current={2}
              items={[
                { title: "Plan" },
                { title: "Retrieve" },
                { title: "Read" },
                { title: "Verify" },
                { title: "Draft" },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </main>
  );
}

