import { useCallback, useEffect, useState } from "react";
import { InboxOutlined, LinkOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Input,
  List,
  Row,
  Space,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadProps } from "antd";

import { PageHeader } from "../components/PageHeader";
import { documentApi, type DocumentSummary } from "../services/documentApi";

const { Text, Paragraph } = Typography;

export function ImportPage() {
  const [url, setUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<DocumentSummary[]>([]);

  const loadRecent = useCallback(async () => {
    try {
      const docs = await documentApi.list();
      setRecent(docs.slice(0, 10));
    } catch {
      // ignore — the queue panel just stays empty
    }
  }, []);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  async function importUrl() {
    if (!url.trim()) return;
    setImporting(true);
    setError(null);
    try {
      const resp = await documentApi.importUrl(url.trim());
      message.success(
        resp.duplicate
          ? "该 URL 已存在，已关联到现有文档"
          : `已创建导入任务（${resp.status}）`,
      );
      setUrl("");
      void loadRecent();
    } catch (e) {
      setError(String(e));
    } finally {
      setImporting(false);
    }
  }

  // File import via the multipart endpoint.
  const uploadProps: UploadProps = {
    multiple: false,
    showUploadList: false,
    customRequest: async (options) => {
      const { file, onSuccess, onError } = options;
      try {
        const resp = await documentApi.importFile(file as File);
        onSuccess?.(resp);
        message.success(`已导入：${resp.status}`);
        void loadRecent();
      } catch (e) {
        onError?.(e as Error);
        message.error(String(e));
      }
    },
  };

  return (
    <main className="page">
      <PageHeader
        title="导入中心"
        description="从本地文件或 URL 导入文档，系统将自动解析、抽取实体与关系。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="文件导入" className="panel-card">
            <Upload.Dragger {...uploadProps}>
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <Typography.Title level={4} style={{ margin: 0 }}>
                将文件拖到这里，或点击上传
              </Typography.Title>
              <Text type="secondary">
                支持 PDF、Word、Excel、图片、Markdown 与 TXT。
              </Text>
            </Upload.Dragger>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="URL 导入" className="panel-card">
            <Space.Compact style={{ width: "100%" }}>
              <Input
                prefix={<LinkOutlined />}
                placeholder="https://example.com/article"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onPressEnter={importUrl}
              />
              <Button type="primary" loading={importing} onClick={importUrl}>
                加入队列
              </Button>
            </Space.Compact>
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
              导入后会自动创建解析任务，提取文本、抽取实体与关系。
            </Paragraph>
          </Card>
        </Col>
      </Row>
      {error && (
        <Alert type="error" message={error} style={{ marginTop: 16 }} />
      )}
      <Card title="最近导入" className="panel-card section-row">
        <List
          dataSource={recent}
          locale={{ emptyText: "还没有导入的文档" }}
          renderItem={(doc) => (
            <List.Item>
              <List.Item.Meta
                title={doc.title}
                description={
                  <Space wrap>
                    <Tag>{doc.source_type}</Tag>
                    <Tag color="blue">{doc.parse_status}</Tag>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Card>
    </main>
  );
}
