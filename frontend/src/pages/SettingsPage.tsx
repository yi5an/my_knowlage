import { useEffect, useState } from "react";

import { Alert, Button, Card, Col, Form, Input, InputNumber, Row, Select, Space, Switch } from "antd";

import { PageHeader } from "../components/PageHeader";
import {
  getAutoRetrySettings,
  updateAutoRetrySettings,
  type YouTubeAutoRetrySettings,
} from "../services/youtubeApi";

const DEFAULT_RETRY_SETTINGS: YouTubeAutoRetrySettings = {
  workspace_id: "ws_default",
  enabled: false,
  max_attempts: 3,
  backoff_minutes: 30,
  batch_size: 1,
};

export function SettingsPage() {
  const [retrySettings, setRetrySettings] = useState<YouTubeAutoRetrySettings>(
    DEFAULT_RETRY_SETTINGS,
  );
  const [loadingRetrySettings, setLoadingRetrySettings] = useState(true);
  const [savingRetrySettings, setSavingRetrySettings] = useState(false);
  const [retrySaveStatus, setRetrySaveStatus] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoadingRetrySettings(true);
    getAutoRetrySettings()
      .then((settings) => {
        if (alive) {
          setRetrySettings(settings);
          setRetryError(null);
        }
      })
      .catch((error: Error) => {
        if (alive) setRetryError(error.message);
      })
      .finally(() => {
        if (alive) setLoadingRetrySettings(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveRetrySettings = async () => {
    setSavingRetrySettings(true);
    setRetrySaveStatus(null);
    setRetryError(null);
    try {
      const saved = await updateAutoRetrySettings({
        enabled: retrySettings.enabled,
        max_attempts: retrySettings.max_attempts,
        backoff_minutes: retrySettings.backoff_minutes,
        batch_size: retrySettings.batch_size,
      });
      setRetrySettings(saved);
      setRetrySaveStatus("已保存");
    } catch (error) {
      setRetryError(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSavingRetrySettings(false);
    }
  };

  return (
    <main className="page">
      <PageHeader
        title="设置"
        description="工作区偏好设置与平台模型管理。API Key 在后端加密保存，不会回显。"
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
          <Card title="模型管理" className="panel-card">
            <Form layout="vertical">
              <p>管理 LLM、Embedding、ASR、OCR 的提供商、模型地址、加密 API Key 和默认路由。</p>
              <Button type="primary" href="/settings/models">打开模型管理</Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="YouTube 自动重试" className="panel-card" loading={loadingRetrySettings}>
            <Form layout="vertical">
              <Form.Item label="启用自动重试">
                <Switch
                  aria-label="启用自动重试"
                  checked={retrySettings.enabled}
                  onChange={(enabled) =>
                    setRetrySettings((current) => ({ ...current, enabled }))
                  }
                />
              </Form.Item>
              <Form.Item label="最大重试次数">
                <InputNumber
                  min={1}
                  max={20}
                  value={retrySettings.max_attempts}
                  onChange={(value) =>
                    setRetrySettings((current) => ({
                      ...current,
                      max_attempts: value ?? DEFAULT_RETRY_SETTINGS.max_attempts,
                    }))
                  }
                />
              </Form.Item>
              <Form.Item label="失败后等待分钟数">
                <InputNumber
                  min={1}
                  max={1440}
                  value={retrySettings.backoff_minutes}
                  onChange={(value) =>
                    setRetrySettings((current) => ({
                      ...current,
                      backoff_minutes: value ?? DEFAULT_RETRY_SETTINGS.backoff_minutes,
                    }))
                  }
                />
              </Form.Item>
              <Form.Item label="每轮重试数量">
                <InputNumber
                  min={1}
                  max={20}
                  value={retrySettings.batch_size}
                  onChange={(value) =>
                    setRetrySettings((current) => ({
                      ...current,
                      batch_size: value ?? DEFAULT_RETRY_SETTINGS.batch_size,
                    }))
                  }
                />
              </Form.Item>
              {retryError ? (
                <Alert type="error" showIcon message={retryError} style={{ marginBottom: 12 }} />
              ) : null}
              <Space>
                <Button
                  type="primary"
                  loading={savingRetrySettings}
                  onClick={saveRetrySettings}
                >
                  保存自动重试配置
                </Button>
                {retrySaveStatus ? <span>{retrySaveStatus}</span> : null}
              </Space>
            </Form>
          </Card>
        </Col>
      </Row>
    </main>
  );
}
