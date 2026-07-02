import { Tag } from "antd";
import type { InfoLayer } from "../../services/investmentApi";

const LAYER_LABEL: Record<InfoLayer, string> = {
  primary_source: "一手信息",
  macro_calendar: "宏观",
  news: "新闻",
  opinion: "观点",
};

const LAYER_COLOR: Record<InfoLayer, string> = {
  primary_source: "geekblue",
  macro_calendar: "purple",
  news: "blue",
  opinion: "orange",
};

export function InfoLayerTag({ layer }: { layer: InfoLayer }) {
  return <Tag color={LAYER_COLOR[layer]}>{LAYER_LABEL[layer]}</Tag>;
}
