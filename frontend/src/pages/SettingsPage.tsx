import { Card, Col, Form, Input, Row, Select, Switch } from "antd";

import { PageHeader } from "../components/PageHeader";

export function SettingsPage() {
  return (
    <main className="page">
      <PageHeader
        title="设置"
        description="工作区偏好设置与提供商占位项，不含 API 密钥。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="工作区" className="panel-card">
            <Form layout="vertical">
              <Form.Item label="工作区名称">
                <Input defaultValue="开发工作区" />
              </Form.Item>
              <Form.Item label="存储模式">
                <Select defaultValue="local" options={[{ label: "本地", value: "local" }]} />
              </Form.Item>
              <Form.Item label="需要证据">
                <Switch defaultChecked />
              </Form.Item>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="模型路由占位项" className="panel-card">
            <Form layout="vertical">
              <Form.Item label="LLM 提供商">
                <Select
                  defaultValue="not_configured"
                  options={[{ label: "未配置", value: "not_configured" }]}
                />
              </Form.Item>
              <Form.Item label="Embedding 提供商">
                <Select
                  defaultValue="not_configured"
                  options={[{ label: "未配置", value: "not_configured" }]}
                />
              </Form.Item>
            </Form>
          </Card>
        </Col>
      </Row>
    </main>
  );
}
