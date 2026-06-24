import { Card, Col, List, Progress, Row, Steps, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";
import { researchTasks } from "../mockData";

export function ResearchPage() {
  return (
    <main className="page">
      <PageHeader
        title="深度研究"
        description="任务列表、报告草稿与 Agent 流程，与文档导入及搜索页面分离。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={7}>
          <Card title="任务" className="panel-card">
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
          <Card title="报告草稿" className="panel-card">
            <Typography.Title level={4}>AI 算力供应链</Typography.Title>
            <Typography.Paragraph>
              早期证据表明，先进光刻、晶圆制造、GPU 设计与云需求是主要的依赖层级。
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={24} lg={7}>
          <Card title="Agent 流程" className="panel-card">
            <Steps
              direction="vertical"
              size="small"
              current={2}
              items={[
                { title: "规划" },
                { title: "检索" },
                { title: "阅读" },
                { title: "验证" },
                { title: "起草" },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </main>
  );
}

