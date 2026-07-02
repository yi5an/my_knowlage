import { Card, Empty, Typography } from "antd";
import { PageHeader } from "../components/PageHeader";

/** Macro calendar view — Phase 2. Stubbed for now; routes are registered. */
export function InvestmentCalendarPage() {
  return (
    <main className="page">
      <PageHeader title="宏观日历" description="宏观事件与经济数据发布日历（开发中）。" />
      <Card>
        <Empty description={<Typography.Text type="secondary">该页面将在第二阶段实现</Typography.Text>} />
      </Card>
    </main>
  );
}
