import { useEffect, useState } from "react";
import { Alert, Button, Card, Col, Form, Input, InputNumber, Row, Select, Space, Table, Tag } from "antd";

import { PageHeader } from "../components/PageHeader";
import { createModel, createProvider, listModels, listProviders, listRoutes, saveRoute, testProvider } from "../services/modelManagementApi";
import type { ManagedModel, ModelCapability, ModelProvider, ModelRoute } from "../types/modelManagement";

const capabilities: { value: ModelCapability; label: string }[] = [
  { value: "llm", label: "LLM" }, { value: "embedding", label: "Embedding" },
  { value: "asr", label: "ASR" }, { value: "ocr", label: "OCR" },
];

export function ModelManagementPage() {
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [models, setModels] = useState<ManagedModel[]>([]);
  const [routes, setRoutes] = useState<ModelRoute[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [providerForm] = Form.useForm();
  const [modelForm] = Form.useForm();

  const reload = () => Promise.all([listProviders(), listModels(), listRoutes()]).then(([p, m, r]) => { setProviders(p); setModels(m); setRoutes(r); });
  useEffect(() => { reload().catch((error: Error) => setMessage(error.message)); }, []);

  const submitProvider = async (testOnly: boolean) => {
    const values = await providerForm.validateFields();
    try {
      if (testOnly) {
        const result = await testProvider({ ...values, model_name: values.test_model_name, capability: values.test_capability });
        setMessage(result.message);
      } else { await createProvider(values); await reload(); setMessage("提供商已保存"); providerForm.resetFields(); }
    } catch (error) { setMessage(error instanceof Error ? error.message : "操作失败"); }
  };
  const submitModel = async () => { try { await createModel(await modelForm.validateFields()); await reload(); setMessage("模型已保存"); modelForm.resetFields(); } catch (error) { setMessage(error instanceof Error ? error.message : "保存失败"); } };

  return <main className="page">
    <PageHeader title="模型管理" description="统一管理 LLM、Embedding、ASR 和 OCR 的地址、密钥与默认路由。密钥仅加密保存，不会回显。" />
    {message ? <Alert closable showIcon message={message} style={{ marginBottom: 16 }} /> : null}
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={12}><Card title="新增提供商"><Form form={providerForm} layout="vertical" initialValues={{ provider_type: "openai_compatible", timeout_seconds: 120, test_capability: "llm" }}>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="provider_type" label="协议" rules={[{ required: true }]}><Select options={[{ value: "openai_compatible", label: "OpenAI 兼容" }, { value: "glm_asr", label: "GLM ASR" }, { value: "knowpilot_ocr", label: "KnowPilot OCR" }]} /></Form.Item>
        <Form.Item name="base_url" label="模型地址" rules={[{ required: true }]}><Input placeholder="https://api.example/v1" /></Form.Item>
        <Form.Item name="api_key" label="API Key"><Input.Password autoComplete="new-password" /></Form.Item>
        <Form.Item name="timeout_seconds" label="超时（秒）"><InputNumber min={1} max={600} /></Form.Item>
        <Form.Item name="test_model_name" label="测试模型" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="test_capability" label="测试能力"><Select options={capabilities} /></Form.Item>
        <Space><Button onClick={() => submitProvider(true)}>测试连接</Button><Button type="primary" onClick={() => submitProvider(false)}>保存提供商</Button></Space>
      </Form></Card></Col>
      <Col xs={24} xl={12}><Card title="新增模型"><Form form={modelForm} layout="vertical">
        <Form.Item name="provider_id" label="提供商" rules={[{ required: true }]}><Select options={providers.filter((p) => p.enabled).map((p) => ({ value: p.id, label: p.name }))} /></Form.Item>
        <Form.Item name="model_name" label="模型名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="model_type" label="能力" rules={[{ required: true }]}><Select options={capabilities} /></Form.Item>
        <Button type="primary" onClick={submitModel}>保存模型</Button>
      </Form></Card></Col>
      <Col span={24}><Card title="提供商"><Table rowKey="id" pagination={false} dataSource={providers} columns={[{ title: "名称", dataIndex: "name" }, { title: "协议", dataIndex: "provider_type" }, { title: "模型地址", dataIndex: "base_url" }, { title: "密钥", render: (_, row: ModelProvider) => row.api_key_configured ? <Tag color="green">{row.api_key_hint ?? "已配置"}</Tag> : <Tag>未配置</Tag> }, { title: "最近测试", render: (_, row: ModelProvider) => row.last_test_message ?? "未测试" }]} /></Card></Col>
      <Col span={24}><Card title="默认模型路由"><Row gutter={[12, 12]}>{capabilities.map(({ value, label }) => <Col xs={24} md={12} key={value}><Form layout="vertical"><Form.Item label={`${label} 默认模型`}><Select value={routes.find((route) => route.capability === value)?.model_config_id} onChange={async (modelId) => { try { await saveRoute(value, modelId); await reload(); setMessage("默认路由已保存"); } catch (error) { setMessage(error instanceof Error ? error.message : "保存失败"); } }} options={models.filter((model) => model.enabled && model.model_type === value).map((model) => ({ value: model.id, label: model.model_name }))} /></Form.Item></Form></Col>)}</Row></Card></Col>
    </Row>
  </main>;
}
