import { ApiOutlined, FileZipOutlined } from "@ant-design/icons";
import { Button, Card, Col, Row, Steps, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";

export function NotebookPage() {
  return (
    <main className="page">
      <PageHeader
        title="NotebookLM"
        description="Prepare export packages and reserve future enterprise API integration settings."
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="Personal export" className="panel-card">
            <Typography.Paragraph>
              Bundle selected documents, summaries, citations, and source manifests into a ZIP.
            </Typography.Paragraph>
            <Button type="primary" icon={<FileZipOutlined />}>
              Prepare package
            </Button>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Enterprise connector" className="panel-card">
            <Typography.Paragraph>
              API endpoint and auth settings are placeholders; no real credentials are stored here.
            </Typography.Paragraph>
            <Button icon={<ApiOutlined />}>Configure</Button>
          </Card>
        </Col>
      </Row>
      <Card title="Export flow" className="panel-card section-row">
        <Steps
          items={[
            { title: "Select" },
            { title: "Validate" },
            { title: "Package" },
            { title: "Export" },
          ]}
        />
      </Card>
    </main>
  );
}

