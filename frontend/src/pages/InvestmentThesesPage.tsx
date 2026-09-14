import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  List,
  Modal,
  message,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { WatchlistSelector } from "../components/investment/WatchlistSelector";
import { ApiError } from "../services/client";
import {
  investmentApi,
  INVESTMENT_WORKSPACE_ID,
  type InvestmentClaim,
  type InvestmentThesis,
  type OpportunityCandidate,
  type InvestmentWatchlist,
} from "../services/investmentApi";

export function InvestmentThesesPage() {
  const [theses, setTheses] = useState<InvestmentThesis[]>([]);
  const [claims, setClaims] = useState<InvestmentClaim[]>([]);
  const [opportunities, setOpportunities] = useState<OpportunityCandidate[]>([]);
  const [watchlists, setWatchlists] = useState<InvestmentWatchlist[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [outcomeOpen, setOutcomeOpen] = useState(false);
  const [form] = Form.useForm();
  const [outcomeForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [t, w, c, o] = await Promise.all([
        investmentApi.listTheses(),
        investmentApi.listWatchlist(),
        investmentApi.listClaims().catch(() => []),
        investmentApi.listOpportunityCandidates({ limit: 100 }).catch(() => []),
      ]);
      setTheses(t);
      setWatchlists(w);
      setClaims(c);
      setOpportunities(o);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreate = async () => {
    const values = await form.validateFields();
    await investmentApi.createThesis({
      title: values.title,
      body: values.body,
      watchlist_id: values.watchlist_id,
      status: values.status ?? "open",
      confidence: values.confidence ?? "medium",
    });
    setOpen(false);
    form.resetFields();
    void load();
  };

  const claimsForThesis = (thesisId: string): InvestmentClaim[] =>
    claims.filter((claim) => claim.thesis_id === thesisId);

  const opportunityForThesis = (thesisId: string): OpportunityCandidate[] => {
    const evidenceRefs = new Set(
      claimsForThesis(thesisId).flatMap((claim) => [claim.id, claim.source_item_id].filter(Boolean)),
    );
    return opportunities.filter((candidate) =>
      candidate.evidence_refs.some((reference) => evidenceRefs.has(reference)),
    );
  };

  const handleRecordOutcome = async () => {
    try {
      const values = await outcomeForm.validateFields();
      await investmentApi.createRecommendationOutcome({
        workspace_id: INVESTMENT_WORKSPACE_ID,
        opportunity_id: values.opportunity_id,
        adopted: Boolean(values.adopted),
        outcome_status: values.outcome_status,
        outcome_note: values.outcome_note || null,
        observed_at: new Date().toISOString(),
      });
      setOutcomeOpen(false);
      outcomeForm.resetFields();
    } catch (cause) {
      if (cause && typeof cause === "object" && "errorFields" in cause) return;
      message.error(cause instanceof ApiError ? cause.message : String(cause));
    }
  };

  return (
    <main className="page">
      <PageHeader
        title="投资假设"
        description="记录并跟踪你的投资假设，信息会按对假设的影响被打分。"
        extra={<Button type="primary" onClick={() => setOpen(true)}>添加假设</Button>}
      />
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}
      <Card>
        <Spin spinning={loading}>
          {theses.length === 0 ? (
            <Empty description="暂无投资假设" />
          ) : (
            <List
              dataSource={theses}
                renderItem={(t) => (
                <List.Item
                  actions={[
                    <Button
                      key="record-outcome"
                      size="small"
                      onClick={() => {
                        const candidate = opportunityForThesis(t.id)[0];
                        outcomeForm.setFieldsValue({ opportunity_id: candidate?.id });
                        setOutcomeOpen(true);
                      }}
                    >
                      记录结果
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <Typography.Text strong>{t.title}</Typography.Text>
                        <Tag>{t.status}</Tag>
                        <Tag color={t.confidence === "high" ? "green" : "default"}>
                          信心：{t.confidence}
                        </Tag>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={4}>
                        {t.body && <span>{t.body}</span>}
                        {claimsForThesis(t.id).length > 0 && (
                          <Typography.Text type="secondary">
                            状态变化证据：
                            {claimsForThesis(t.id)
                              .map((claim) => `${claim.claim_text}（${claim.verification_status}）`)
                              .join("；")}
                          </Typography.Text>
                        )}
                        {opportunityForThesis(t.id)[0] && (
                          <Typography.Text type="secondary">
                            关联机会：{opportunityForThesis(t.id)[0].title}
                          </Typography.Text>
                        )}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Spin>
      </Card>

      <Modal
        open={outcomeOpen}
        title="记录假设结果"
        onCancel={() => setOutcomeOpen(false)}
        onOk={() => void handleRecordOutcome()}
        okText="保存结果"
        cancelText="取消"
      >
        <Form form={outcomeForm} layout="vertical">
          <Form.Item label="关联机会" name="opportunity_id" rules={[{ required: true, message: "请选择机会候选" }]}>
            <Select
              placeholder="选择要复盘的机会"
              options={opportunities.map((candidate) => ({ value: candidate.id, label: candidate.title }))}
              notFoundContent="暂无可复盘机会"
            />
          </Form.Item>
          <Form.Item label="结果" name="outcome_status" initialValue="validated">
            <Select
              options={[
                { value: "validated", label: "已验证" },
                { value: "invalidated", label: "已证伪" },
                { value: "expired", label: "已过期" },
                { value: "tracking", label: "继续跟踪" },
              ]}
            />
          </Form.Item>
          <Form.Item label="是否采用" name="adopted" initialValue={false}>
            <Select options={[{ value: true, label: "已采用" }, { value: false, label: "未采用" }]} />
          </Form.Item>
          <Form.Item label="结果备注" name="outcome_note">
            <Input.TextArea rows={3} placeholder="记录催化剂是否兑现、失败原因或下一步。" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={open}
        title="添加投资假设"
        onCancel={() => setOpen(false)}
        onOk={handleCreate}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item label="标题" name="title" rules={[{ required: true }]}>
            <Input placeholder="如：AI 需求持续强劲" />
          </Form.Item>
          <Form.Item label="关联观察对象" name="watchlist_id">
            <WatchlistSelector watchlists={watchlists} />
          </Form.Item>
          <Form.Item label="状态" name="status" initialValue="open">
            <Select
              options={[
                { value: "open", label: "进行中" },
                { value: "closed", label: "已关闭" },
                { value: "invalidated", label: "已证伪" },
              ]}
            />
          </Form.Item>
          <Form.Item label="信心" name="confidence" initialValue="medium">
            <Select
              options={[
                { value: "low", label: "低" },
                { value: "medium", label: "中" },
                { value: "high", label: "高" },
              ]}
            />
          </Form.Item>
          <Form.Item label="假设内容" name="body">
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>
    </main>
  );
}
