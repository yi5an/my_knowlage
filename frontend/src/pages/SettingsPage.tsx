import { Card, Col, Form, Input, Row, Select, Switch } from "antd";

import { PageHeader } from "../components/PageHeader";

export function SettingsPage() {
  return (
    <main className="page">
      <PageHeader
        title="Settings"
        description="Workspace preferences and provider placeholders without API keys."
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="Workspace" className="panel-card">
            <Form layout="vertical">
              <Form.Item label="Workspace name">
                <Input defaultValue="Development Workspace" />
              </Form.Item>
              <Form.Item label="Storage mode">
                <Select defaultValue="local" options={[{ label: "Local", value: "local" }]} />
              </Form.Item>
              <Form.Item label="Evidence required">
                <Switch defaultChecked />
              </Form.Item>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Model routing placeholders" className="panel-card">
            <Form layout="vertical">
              <Form.Item label="LLM provider">
                <Select
                  defaultValue="not_configured"
                  options={[{ label: "Not configured", value: "not_configured" }]}
                />
              </Form.Item>
              <Form.Item label="Embedding provider">
                <Select
                  defaultValue="not_configured"
                  options={[{ label: "Not configured", value: "not_configured" }]}
                />
              </Form.Item>
            </Form>
          </Card>
        </Col>
      </Row>
    </main>
  );
}
