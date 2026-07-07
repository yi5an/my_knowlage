import {
  Button,
  DatePicker,
  Divider,
  Drawer,
  Form,
  Input,
  Select,
  Space,
  Typography,
  message,
} from "antd";
import { useEffect, useState } from "react";
import {
  investmentApi,
  type ActionStatus,
  type ImpactDirection,
  type ImpactHorizon,
  type Importance,
  type InvestmentItem,
  type ThesisImpact,
} from "../../services/investmentApi";
import { InfoLayerTag } from "./InfoLayerTag";

const IMPORTANCE_OPTS: Importance[] = ["low", "medium", "high"];
const IMPACT_DIR_OPTS: ImpactDirection[] = ["positive", "negative", "neutral", "uncertain"];
const IMPACT_HORIZON_OPTS: ImpactHorizon[] = ["short", "mid", "long", "unknown"];
const THESIS_IMPACT_OPTS: ThesisImpact[] = [
  "supports",
  "weakens",
  "contradicts",
  "unrelated",
  "unknown",
];
const STATUS_OPTS: ActionStatus[] = [
  "pending_review",
  "tracking",
  "ignored",
  "researched",
  "archived",
];

const ZH: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  positive: "利好",
  negative: "利空",
  neutral: "中性",
  uncertain: "不确定",
  short: "短期",
  mid: "中期",
  long: "长期",
  unknown: "未知",
  supports: "支持",
  weakens: "削弱",
  contradicts: "反驳",
  unrelated: "无关",
  pending_review: "待审阅",
  tracking: "跟踪中",
  ignored: "忽略",
  researched: "已研究",
  archived: "已归档",
};

/**
 * Detail + edit drawer for an investment item. Editing writes the
 * user-confirmed impact fields (importance / direction / horizon / thesis_impact
 * / status); auto-classified suggestions are shown read-only.
 */
export function InvestmentItemDrawer({
  item,
  open,
  onClose,
  onUpdated,
}: {
  item: InvestmentItem | null;
  open: boolean;
  onClose: () => void;
  onUpdated?: () => void;
}) {
  const [form] = Form.useForm();
  const [classifying, setClassifying] = useState(false);
  const displaySummary = item?.summary_zh ?? item?.summary;
  const originalSummary =
    item?.summary_zh && item.summary && item.summary_zh !== item.summary ? item.summary : null;
  const attachments = item?.attachments ?? [];

  useEffect(() => {
    if (item) {
      form.setFieldsValue({
        source: item.source_name
          ? `${item.source_name}${item.source_url ? ` · ${item.source_url}` : ""}`
          : "",
        title: item.title,
        summary: item.summary ?? "",
        importance: item.importance,
        impact_direction: item.impact_direction,
        impact_horizon: item.impact_horizon,
        thesis_impact: item.thesis_impact,
        action_status: item.action_status,
        review_at: item.review_at ? undefined : undefined,
      });
    }
  }, [item, form]);

  if (!item) return null;

  const handleSave = async () => {
    const values = await form.validateFields();
    await investmentApi.updateItem(item.id, values);
    onUpdated?.();
    onClose();
  };

  const handleClassify = async () => {
    setClassifying(true);
    try {
      await investmentApi.classifyItem(item.id);
      message.success("自动分类完成");
      onUpdated?.();
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error));
    } finally {
      setClassifying(false);
    }
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={
        <Space>
          <span>{item.title_zh ?? item.title}</span>
          <InfoLayerTag layer={item.info_layer} />
        </Space>
      }
      width={520}
      footer={
        <Space style={{ float: "right" }}>
          <Button loading={classifying} onClick={handleClassify}>
            自动分类
          </Button>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={handleSave}>
            保存
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <div>
          <Typography.Text type="secondary">来源</Typography.Text>
          <div style={{ marginTop: 4 }}>
            <Typography.Text>{item.source_name ?? "未知来源"}</Typography.Text>
            {item.source_url && (
              <Button
                type="link"
                href={item.source_url}
                target="_blank"
                rel="noreferrer"
                style={{ paddingInline: 8 }}
              >
                打开源站原文
              </Button>
            )}
          </div>
        </div>

        <div>
          <Typography.Title level={5} style={{ marginBottom: 8 }}>
            内容详情
          </Typography.Title>
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>
            {displaySummary || "暂无内容摘要。"}
          </Typography.Paragraph>
          {originalSummary && (
            <>
              <Typography.Text type="secondary">原文摘要</Typography.Text>
              <Typography.Paragraph
                type="secondary"
                style={{ whiteSpace: "pre-wrap", marginTop: 4, marginBottom: 0 }}
              >
                {originalSummary}
              </Typography.Paragraph>
            </>
          )}
        </div>

        {attachments.length > 0 && (
          <div>
            <Typography.Title level={5} style={{ marginBottom: 8 }}>
              附件
            </Typography.Title>
            <Space direction="vertical" size={10} style={{ width: "100%" }}>
              {attachments.map((attachment) => (
                <div key={attachment.url}>
                  <Typography.Link href={attachment.url} target="_blank" rel="noreferrer">
                    {attachment.title}
                  </Typography.Link>
                  {attachment.content_type && (
                    <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
                      {attachment.content_type.toUpperCase()}
                    </Typography.Text>
                  )}
                  {attachment.text_excerpt && (
                    <Typography.Paragraph
                      type="secondary"
                      style={{ whiteSpace: "pre-wrap", marginTop: 4, marginBottom: 0 }}
                    >
                      {attachment.text_excerpt}
                    </Typography.Paragraph>
                  )}
                </div>
              ))}
            </Space>
          </div>
        )}
      </Space>

      <Divider />

      <Form form={form} layout="vertical">
        <Form.Item label="来源" name="source">
          <Input
            disabled
            value={
              item.source_name
                ? `${item.source_name}${item.source_url ? ` · ${item.source_url}` : ""}`
                : ""
            }
          />
        </Form.Item>
        <Form.Item label="标题" name="title">
          <Input />
        </Form.Item>
        <Form.Item label="摘要" name="summary">
          <Input.TextArea rows={4} />
        </Form.Item>
        <Form.Item label="重要性" name="importance">
          <Select options={IMPORTANCE_OPTS.map((v) => ({ value: v, label: ZH[v] }))} />
        </Form.Item>
        <Form.Item label="影响方向" name="impact_direction">
          <Select options={IMPACT_DIR_OPTS.map((v) => ({ value: v, label: ZH[v] }))} />
        </Form.Item>
        <Form.Item label="影响周期" name="impact_horizon">
          <Select options={IMPACT_HORIZON_OPTS.map((v) => ({ value: v, label: ZH[v] }))} />
        </Form.Item>
        <Form.Item label="对假设影响" name="thesis_impact">
          <Select options={THESIS_IMPACT_OPTS.map((v) => ({ value: v, label: ZH[v] }))} />
        </Form.Item>
        <Form.Item label="处理状态" name="action_status">
          <Select options={STATUS_OPTS.map((v) => ({ value: v, label: ZH[v] }))} />
        </Form.Item>
        <Form.Item label="复查日期" name="review_at">
          <DatePicker showTime style={{ width: "100%" }} />
        </Form.Item>

        {(item.suggested_importance ||
          item.suggested_impact_direction ||
          item.classification_reason) && (
          <Form.Item label="自动分类建议（仅供参考）">
            <div style={{ color: "#8c8c8c", fontSize: 12 }}>
              {item.suggested_importance && <div>建议重要性：{ZH[item.suggested_importance] ?? item.suggested_importance}</div>}
              {item.suggested_impact_direction && (
                <div>建议影响方向：{ZH[item.suggested_impact_direction] ?? item.suggested_impact_direction}</div>
              )}
              {item.classification_reason && <div>理由：{item.classification_reason}</div>}
            </div>
          </Form.Item>
        )}
      </Form>
    </Drawer>
  );
}
