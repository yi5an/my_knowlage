import { ApiOutlined, FileZipOutlined } from "@ant-design/icons";
import { Button, Card, Col, Row, Steps, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";

export function NotebookPage() {
  return (
    <main className="page">
      <PageHeader
        title="NotebookLM"
        description="准备导出包，并预留未来企业 API 集成设置。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="个人导出" className="panel-card">
            <Typography.Paragraph>
              将选中的文档、摘要、引用与来源清单打包为 ZIP。
            </Typography.Paragraph>
            <Button type="primary" icon={<FileZipOutlined />}>
              准备打包
            </Button>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="企业连接器" className="panel-card">
            <Typography.Paragraph>
              API 端点与认证设置为占位项，此处不存储真实凭证。
            </Typography.Paragraph>
            <Button icon={<ApiOutlined />}>配置</Button>
          </Card>
        </Col>
      </Row>
      <Card title="导出流程" className="panel-card section-row">
        <Steps
          items={[
            { title: "选择" },
            { title: "校验" },
            { title: "打包" },
            { title: "导出" },
          ]}
        />
      </Card>
    </main>
  );
}

