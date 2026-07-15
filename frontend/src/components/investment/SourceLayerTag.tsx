import { Tag } from "antd";
import type { SourceLayer } from "../../services/investmentApi";

const LAYER_LABEL: Record<SourceLayer, string> = {
  primary_source: "一手源",
  human_source: "人源",
  expert_opinion: "专家观点",
  news_confirmation: "新闻确认",
  market_feedback: "市场反馈",
};

const LAYER_COLOR: Record<SourceLayer, string> = {
  primary_source: "geekblue",
  human_source: "gold",
  expert_opinion: "orange",
  news_confirmation: "blue",
  market_feedback: "green",
};

export function SourceLayerTag({ layer }: { layer: SourceLayer }) {
  return <Tag color={LAYER_COLOR[layer]}>{LAYER_LABEL[layer]}</Tag>;
}
