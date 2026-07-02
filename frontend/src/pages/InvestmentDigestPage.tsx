import { Card, Empty, Typography } from "antd";
import { PageHeader } from "../components/PageHeader";

/** Daily/periodic digest view — Phase 2. Stubbed for now; routes are registered. */
export function InvestmentDigestPage() {
  return (
    <main className="page">
      <PageHeader title="每日简报" description="投资信息每日摘要（开发中）。" />
      <Card>
        <Empty description={<Typography.Text type="secondary">该页面将在第二阶段实现</Typography.Text>} />
      </Card>
    </main>
  );
}
