import { Card, Input, List, Space, Tag, Typography } from "antd";

import { PageHeader } from "../components/PageHeader";
import { citations } from "../mockData";

export function SearchPage() {
  return (
    <main className="page">
      <PageHeader
        title="Smart search"
        description="Preview AI answers, citations, and retrieval context using mock data."
      />
      <Input.Search
        size="large"
        defaultValue="What role does GraphRAG play in KnowPilot?"
        enterButton="Ask"
      />
      <Card title="AI answer" className="panel-card section-row">
        <Typography.Paragraph>
          GraphRAG links chunks, entities, and relations so answers can combine semantic retrieval
          with explicit graph evidence.
        </Typography.Paragraph>
        <Space wrap>
          <Tag color="green">confidence 0.86</Tag>
          <Tag color="blue">2 citations</Tag>
        </Space>
      </Card>
      <Card title="Citations" className="panel-card section-row">
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

