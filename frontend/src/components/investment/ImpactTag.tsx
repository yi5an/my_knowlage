import { Tag } from "antd";
import type { ImpactDirection } from "../../services/investmentApi";

const DIRECTION_LABEL: Record<ImpactDirection, string> = {
  positive: "利好",
  negative: "利空",
  neutral: "中性",
  uncertain: "不确定",
};

const DIRECTION_COLOR: Record<ImpactDirection, string> = {
  positive: "success",
  negative: "error",
  neutral: "default",
  uncertain: "warning",
};

export function ImpactTag({ direction }: { direction: ImpactDirection }) {
  return <Tag color={DIRECTION_COLOR[direction]}>{DIRECTION_LABEL[direction]}</Tag>;
}
