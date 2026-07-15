import { Tag } from "antd";
import type { InvestmentItem } from "../../services/investmentApi";

const CJK_RE = /[\u4e00-\u9fff]/;

function looksChinese(text?: string | null): boolean {
  return Boolean(text && CJK_RE.test(text));
}

function needsTranslation(item: InvestmentItem): boolean {
  const titleNeedsTranslation = !item.title_zh && !looksChinese(item.title);
  const summaryNeedsTranslation = Boolean(
    item.summary && !item.summary_zh && !looksChinese(item.summary),
  );
  return titleNeedsTranslation || summaryNeedsTranslation;
}

export function TranslationStatusTag({ item }: { item: InvestmentItem }) {
  if (!needsTranslation(item)) return null;
  return <Tag color="warning">待翻译</Tag>;
}
