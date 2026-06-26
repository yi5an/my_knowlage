import { useState } from "react";
import {
  Alert,
  Card,
  Empty,
  Input,
  List,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";

import { PageHeader } from "../components/PageHeader";
import { searchApi, type ChatAnswer } from "../services/searchApi";

const { Paragraph, Text } = Typography;

export function SearchPage() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ChatAnswer | null>(null);

  async function ask() {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const answer = await searchApi.ask(question.trim());
      setResult(answer);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  const avgConfidence =
    result && result.citations.length > 0
      ? result.citations.reduce((s, c) => s + c.confidence, 0) / result.citations.length
      : 0;

  return (
    <main className="page">
      <PageHeader
        title="智能搜索"
        description="基于知识库的 RAG 问答：检索相关文档片段与实体，生成带引用的回答。"
      />
      <Input.Search
        size="large"
        placeholder="提出你的问题，例如：AI 基建产业链有哪些关键环节？"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        enterButton="提问"
        loading={loading}
        onSearch={ask}
        style={{ marginBottom: 16 }}
      />
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
      {loading && (
        <Card className="panel-card">
          <Skeleton active paragraph={{ rows: 4 }} />
        </Card>
      )}
      {!loading && result && (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Card title="AI 回答" className="panel-card">
            <Paragraph style={{ whiteSpace: "pre-wrap" }}>{result.answer}</Paragraph>
            <Space wrap>
              {avgConfidence > 0 && (
                <Tag color="green">平均置信度 {avgConfidence.toFixed(2)}</Tag>
              )}
              <Tag color="blue">{result.citations.length} 条引用</Tag>
              {result.related_entities.length > 0 && (
                <Tag color="purple">{result.related_entities.length} 个相关实体</Tag>
              )}
            </Space>
          </Card>
          {result.related_entities.length > 0 && (
            <Card title="相关实体" className="panel-card">
              <Space wrap>
                {result.related_entities.map((e) => (
                  <Tag key={e.entity_id} color="geekblue">
                    {e.name}
                  </Tag>
                ))}
              </Space>
            </Card>
          )}
          <Card title="引用" className="panel-card">
            {result.citations.length === 0 ? (
              <Empty description="无引用" />
            ) : (
              <List
                dataSource={result.citations}
                renderItem={(c, i) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <Space>
                          <Text type="secondary">[{i + 1}]</Text>
                          <Text>{c.title}</Text>
                          <Tag color="green">{c.confidence.toFixed(2)}</Tag>
                        </Space>
                      }
                      description={c.quote}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Space>
      )}
      {!loading && !result && !error && (
        <Card className="panel-card">
          <Empty description="输入问题后点击提问，获取基于知识库的回答。" />
        </Card>
      )}
    </main>
  );
}
