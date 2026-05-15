import { InboxOutlined, LinkOutlined } from "@ant-design/icons";
import { Button, Card, Col, Input, Progress, Row, Space, Table, Tag, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";
import { importJobs } from "../mockData";

export function ImportPage() {
  return (
    <main className="page">
      <PageHeader
        title="Import center"
        description="Prepare local files, URLs, and parsing tasks before they become library documents."
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="File import" className="panel-card">
            <div className="drop-zone">
              <InboxOutlined />
              <Typography.Title level={4}>Drop files here</Typography.Title>
              <Typography.Text type="secondary">
                PDF, Word, Excel, images, Markdown, and TXT are supported by future import workers.
              </Typography.Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="URL import" className="panel-card">
            <Space.Compact className="url-import">
              <Input prefix={<LinkOutlined />} placeholder="https://example.com/article" />
              <Button type="primary">Queue</Button>
            </Space.Compact>
            <Space wrap className="tag-row">
              <Tag color="blue">snapshot</Tag>
              <Tag color="green">summary</Tag>
              <Tag color="gold">entities</Tag>
              <Tag color="purple">relations</Tag>
            </Space>
          </Card>
        </Col>
      </Row>
      <Card title="Import task queue" className="panel-card section-row">
        <Table
          pagination={false}
          dataSource={importJobs}
          rowKey="name"
          columns={[
            { title: "Source", dataIndex: "name" },
            { title: "Status", dataIndex: "status" },
            {
              title: "Progress",
              dataIndex: "progress",
              render: (value: number) => <Progress percent={value} size="small" />,
            },
          ]}
        />
      </Card>
    </main>
  );
}

