import {
  Button,
  DatePicker,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from "antd";
import { useEffect, useState } from "react";
import {
  investmentApi,
  type ActionStatus,
  type ImpactDirection,
  type ImpactHorizon,
  type InvestmentFact,
  type Importance,
  type InvestmentItem,
  type OpportunityCandidate,
  type ThesisImpact,
} from "../../services/investmentApi";
import { InfoLayerTag } from "./InfoLayerTag";
import { TranslationStatusTag } from "./TranslationStatusTag";

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
  pending: "待验证",
  verifying: "验证中",
  verified: "已验证",
  refuted: "已证伪",
  local_only: "仅本地证据",
};

/**
 * Detail + edit drawer for an investment item. Editing writes the
 * user-confirmed impact fields (importance / direction / horizon / thesis_impact
 * / status); auto-classified suggestions are shown read-only.
 */
export function InvestmentItemDrawer({
  item,
  opportunity = null,
  open,
  onClose,
  onUpdated,
}: {
  item: InvestmentItem | null;
  opportunity?: OpportunityCandidate | null;
  open: boolean;
  onClose: () => void;
  onUpdated?: () => void;
}) {
  const [form] = Form.useForm();
  const [classifying, setClassifying] = useState(false);
  const [facts, setFacts] = useState<InvestmentFact[]>([]);
  const [factsLoading, setFactsLoading] = useState(false);
  const [factsError, setFactsError] = useState<string | null>(null);
  const [opportunityUpdating, setOpportunityUpdating] = useState(false);
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

  useEffect(() => {
    if (!item || !open) {
      setFacts([]);
      setFactsError(null);
      return;
    }
    setFactsLoading(true);
    setFactsError(null);
    investmentApi
      .listItemFacts(item.id)
      .then(setFacts)
      .catch((error: unknown) =>
        setFactsError(error instanceof Error ? error.message : String(error)),
      )
      .finally(() => setFactsLoading(false));
  }, [item, open]);

  if (!item && !opportunity) return null;

  const handleSave = async () => {
    if (!item) return;
    const values = await form.validateFields();
    await investmentApi.updateItem(item.id, values);
    onUpdated?.();
    onClose();
  };

  const handleClassify = async () => {
    if (!item) return;
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

  const handleOpportunityReview = async (
    status: "researching" | "waiting_for_evidence" | "parked",
    successMessage: string,
  ) => {
    if (!opportunity) return;
    setOpportunityUpdating(true);
    try {
      await investmentApi.reviewOpportunityCandidate(opportunity.id, { status }, opportunity.workspace_id);
      message.success(successMessage);
      onUpdated?.();
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error));
    } finally {
      setOpportunityUpdating(false);
    }
  };

  const opportunitySourceUrl = opportunity?.evidence_refs.find((reference) =>
    /^https?:\/\//i.test(reference),
  );

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={
        <Space>
          <span>{item?.title_zh ?? item?.title ?? opportunity?.title}</span>
          {item && <InfoLayerTag layer={item.info_layer} />}
          {item && <TranslationStatusTag item={item} />}
        </Space>
      }
      width={520}
      footer={
        <Space style={{ float: "right" }}>
          {item && (
            <>
              <Button loading={classifying} onClick={handleClassify}>
                自动分类
              </Button>
              <Button onClick={onClose}>取消</Button>
              <Button type="primary" onClick={handleSave}>
                保存
              </Button>
            </>
          )}
          {opportunity && <Button onClick={onClose}>关闭</Button>}
        </Space>
      }
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        {opportunity && (
          <div className="opportunity-drawer-section">
            <Typography.Title level={5} style={{ marginBottom: 8 }}>
              机会候选详情
            </Typography.Title>
            <Space direction="vertical" size={10} style={{ width: "100%" }}>
              <Space wrap>
                <Tag color="blue">置信度 {Math.round(opportunity.confidence * 100)}%</Tag>
                <Tag>市场反应：{opportunity.market_reaction_state || "未知"}</Tag>
                {opportunity.asset_symbols.map((symbol) => (
                  <Tag key={symbol} color="cyan">
                    {symbol}
                  </Tag>
                ))}
              </Space>
              <div>
                <Typography.Text type="secondary">来源摘录 / 证据引用</Typography.Text>
                <Space direction="vertical" size={2} style={{ width: "100%", marginTop: 4 }}>
                  {opportunity.evidence_refs.length > 0 ? (
                    opportunity.evidence_refs.map((reference) => (
                      <Typography.Text key={reference} ellipsis>
                        {/^(https?:\/\/)/i.test(reference) ? (
                          <Typography.Link href={reference} target="_blank" rel="noreferrer">
                            {reference}
                          </Typography.Link>
                        ) : (
                          <Typography.Link href={`/investment/items?item_id=${encodeURIComponent(reference)}`}>
                            {reference}
                          </Typography.Link>
                        )}
                      </Typography.Text>
                    ))
                  ) : (
                    <Typography.Text type="secondary">暂无证据引用</Typography.Text>
                  )}
                </Space>
              </div>
              <Descriptions
                size="small"
                column={1}
                colon={false}
                items={[
                  { key: "expected-case", label: "预期情景", children: opportunity.expected_case },
                  { key: "market-case", label: "市场情景", children: opportunity.market_case },
                  { key: "catalyst", label: "催化剂", children: opportunity.catalyst },
                  {
                    key: "risks",
                    label: "风险",
                    children:
                      opportunity.risk_flags.length > 0
                        ? opportunity.risk_flags.join("；")
                        : "暂无已知风险",
                  },
                  {
                    key: "invalidation",
                    label: "失效条件",
                    children:
                      opportunity.invalidation_conditions.length > 0
                        ? opportunity.invalidation_conditions.join("；")
                        : "尚未定义失效条件",
                  },
                  { key: "next-action", label: "建议下一步", children: opportunity.next_action },
                ]}
              />
              <Space wrap>
                <Button
                  size="small"
                  loading={opportunityUpdating}
                  onClick={() => void handleOpportunityReview("researching", "已加入验证队列")}
                >
                  加入验证
                </Button>
                <Button
                  size="small"
                  loading={opportunityUpdating}
                  onClick={() =>
                    void handleOpportunityReview("waiting_for_evidence", "已设为继续观察")
                  }
                >
                  继续观察
                </Button>
                <Button
                  size="small"
                  onClick={() => message.info("研究任务已记录，可在研究简报中继续")}
                >
                  建立研究任务
                </Button>
                <Button
                  size="small"
                  loading={opportunityUpdating}
                  onClick={() => void handleOpportunityReview("parked", "已忽略该机会候选")}
                >
                  忽略
                </Button>
                <Button
                  size="small"
                  type="link"
                  href={opportunitySourceUrl}
                  target={opportunitySourceUrl ? "_blank" : undefined}
                  rel={opportunitySourceUrl ? "noreferrer" : undefined}
                  onClick={(event) => {
                    if (!opportunitySourceUrl) {
                      event.preventDefault();
                      message.info("当前证据引用没有可打开的原文链接");
                    }
                  }}
                >
                  打开原文
                </Button>
              </Space>
            </Space>
          </div>
        )}
        {item && (
          <>
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

        <div>
          <Typography.Title level={5} style={{ marginBottom: 8 }}>
            事实点
          </Typography.Title>
          <Spin spinning={factsLoading}>
            {factsError ? (
              <Typography.Text type="danger">{factsError}</Typography.Text>
            ) : facts.length === 0 ? (
              <Empty description="暂无结构化事实" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Space direction="vertical" size={10} style={{ width: "100%" }}>
                {facts.map((fact) => (
                  <div
                    key={fact.id}
                    style={{
                      border: "1px solid #f0f0f0",
                      borderRadius: 6,
                      padding: 10,
                    }}
                  >
                    <Space size={[4, 4]} wrap style={{ marginBottom: 4 }}>
                      <Tag>{fact.fact_type}</Tag>
                      <Tag color="blue">置信度 {Math.round(fact.confidence * 100)}%</Tag>
                      <Tag>{ZH[fact.verification_status] ?? fact.verification_status}</Tag>
                    </Space>
                    <Typography.Paragraph style={{ marginBottom: 4 }}>
                      {fact.fact_text_zh ?? fact.fact_text}
                    </Typography.Paragraph>
                    <Typography.Paragraph
                      type="secondary"
                      style={{ whiteSpace: "pre-wrap", marginBottom: 4 }}
                    >
                      证据：{fact.evidence_excerpt}
                    </Typography.Paragraph>
                    {fact.evidence_url && (
                      <Typography.Link href={fact.evidence_url} target="_blank" rel="noreferrer">
                        打开证据来源
                      </Typography.Link>
                    )}
                  </div>
                ))}
              </Space>
            )}
          </Spin>
        </div>
          </>
        )}
      </Space>

      {item && <Divider />}

      {item && <Form form={form} layout="vertical">
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
      </Form>}
    </Drawer>
  );
}
