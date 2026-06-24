import { Card, Input, List, Space, Tag, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";
import { citations } from "../mockData";

export function SearchPage() {
  return (
    <main className="page">
      <PageHeader
        title="智能搜索"
        description="使用演示数据预览 AI 回答、引用和检索上下文。"
      />
      <Input.Search
        size="large"
        defaultValue="GraphRAG 在 KnowPilot 中扮演什么角色？"
        enterButton="提问"
      />
      <Card title="AI 回答" className="panel-card section-row">
        <Typography.Paragraph>
          GraphRAG 将文本块、实体和关系关联起来，使回答能结合语义检索与显式图谱证据。
        </Typography.Paragraph>
        <Space wrap>
          <Tag color="green">置信度 0.86</Tag>
          <Tag color="blue">2 条引用</Tag>
        </Space>
      </Card>
      <Card title="引用" className="panel-card section-row">
        <List
          dataSource={citations}
          renderItem={(citation) => (
            <List.Item>
              <List.Item.Meta title={citation.source} description={citation.quote} />
            </List.Item>
          )}
        />
      </Card>
    </main>
  );
}

