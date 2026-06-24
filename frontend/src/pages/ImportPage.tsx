import { InboxOutlined, LinkOutlined } from "@ant-design/icons";
import { Button, Card, Col, Input, Progress, Row, Space, Table, Tag, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";
import { importJobs } from "../mockData";

export function ImportPage() {
  return (
    <main className="page">
      <PageHeader
        title="导入中心"
        description="在本地文件、URL 与解析任务成为文档库文档之前进行准备。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="文件导入" className="panel-card">
            <div className="drop-zone">
              <InboxOutlined />
              <Typography.Title level={4}>将文件拖到这里</Typography.Title>
              <Typography.Text type="secondary">
                未来的导入工作器将支持 PDF、Word、Excel、图片、Markdown 与 TXT。
              </Typography.Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="URL 导入" className="panel-card">
            <Space.Compact className="url-import">
              <Input prefix={<LinkOutlined />} placeholder="https://example.com/article" />
              <Button type="primary">加入队列</Button>
            </Space.Compact>
            <Space wrap className="tag-row">
              <Tag color="blue">快照</Tag>
              <Tag color="green">摘要</Tag>
              <Tag color="gold">实体</Tag>
              <Tag color="purple">关系</Tag>
            </Space>
          </Card>
        </Col>
      </Row>
      <Card title="导入任务队列" className="panel-card section-row">
        <Table
          pagination={false}
          dataSource={importJobs}
          rowKey="name"
          columns={[
            { title: "来源", dataIndex: "name" },
            { title: "状态", dataIndex: "status" },
            {
              title: "进度",
              dataIndex: "progress",
              render: (value: number) => <Progress percent={value} size="small" />,
            },
          ]}
        />
      </Card>
    </main>
  );
}

