import { Tag } from "antd";
import type { ActionStatus } from "../../services/investmentApi";

const STATUS_LABEL: Record<ActionStatus, string> = {
  pending_review: "待审阅",
  tracking: "跟踪中",
  ignored: "忽略",
  researched: "已研究",
  archived: "已归档",
};

const STATUS_COLOR: Record<ActionStatus, string> = {
  pending_review: "warning",
  tracking: "processing",
  ignored: "default",
  researched: "success",
  archived: "default",
};

export function ReviewStatusTag({ status }: { status: ActionStatus }) {
  return <Tag color={STATUS_COLOR[status]}>{STATUS_LABEL[status]}</Tag>;
}
