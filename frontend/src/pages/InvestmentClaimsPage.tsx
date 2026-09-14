import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { WatchlistSelector } from "../components/investment/WatchlistSelector";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type InvestmentClaim,
  type InvestmentItem,
  type OpportunityCandidate,
  type InvestmentThesis,
  type InvestmentWatchlist,
  type VerificationStatus,
} from "../services/investmentApi";

const VERIF_LABEL: Record<VerificationStatus, string> = {
  pending: "待验证",
  verifying: "验证中",
  verified: "已证实",
  refuted: "已证伪",
  local_only: "仅本地证据",
  ignored: "已忽略",
};

const VERIF_COLOR: Record<VerificationStatus, string> = {
  pending: "warning",
  verifying: "processing",
  verified: "success",
  refuted: "error",
  local_only: "default",
  ignored: "default",
};

const MANUAL_STATUS_ACTIONS: Array<{
  label: string;
  status: VerificationStatus;
  summary: string;
}> = [
  { label: "证实", status: "verified", summary: "人工标记为已证实" },
  { label: "证伪", status: "refuted", summary: "人工标记为已证伪" },
  { label: "仅本地", status: "local_only", summary: "人工标记为仅本地证据" },
  { label: "忽略", status: "ignored", summary: "人工忽略" },
];

export function InvestmentClaimsPage() {
  const [claims, setClaims] = useState<InvestmentClaim[]>([]);
  const [watchlists, setWatchlists] = useState<InvestmentWatchlist[]>([]);
  const [theses, setTheses] = useState<InvestmentThesis[]>([]);
  const [opportunities, setOpportunities] = useState<OpportunityCandidate[]>([]);
  const [items, setItems] = useState<InvestmentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [verifying, setVerifying] = useState<Record<string, boolean>>({});
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, w, t, o, i] = await Promise.all([
        investmentApi.listClaims(),
        investmentApi.listWatchlist(),
        investmentApi.listTheses(),
        investmentApi.listOpportunityCandidates({ limit: 100 }).catch(() => []),
        investmentApi.listItems({ limit: 200 }).catch(() => []),
      ]);
      setClaims(c);
      setWatchlists(w);
      setTheses(t);
      setOpportunities(o);
      setItems(i);
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
    await investmentApi.createClaim({
      claim_text: values.claim_text,
      watchlist_id: values.watchlist_id,
      thesis_id: values.thesis_id,
      required_evidence: values.required_evidence
        ? String(values.required_evidence).split("\n").map((s: string) => s.trim()).filter(Boolean)
        : [],
    });
    setOpen(false);
    form.resetFields();
    void load();
  };

  const evidenceGroup = (claim: InvestmentClaim): string => {
    if (claim.verification_status === "verified") return "支持";
    if (claim.verification_status === "refuted") return "冲突";
    if (claim.verification_status === "ignored") return "无关";
    if (claim.verification_status === "local_only") return "削弱";
    return "还不确定";
  };

  const linkedOpportunity = (claim: InvestmentClaim): OpportunityCandidate | undefined =>
    opportunities.find(
      (candidate) =>
        candidate.evidence_refs.includes(claim.id) ||
        (claim.source_item_id ? candidate.evidence_refs.includes(claim.source_item_id) : false),
    );

  const evidenceReferences = (claim: InvestmentClaim): string[] =>
    Array.from(
      new Set([
        ...(claim.evidence_refs ?? []),
        ...(claim.evidence_doc_ids ?? []),
        ...(claim.source_item_id ? [claim.source_item_id] : []),
      ]),
    );

  const evidenceUrl = (reference: string): string | null => {
    if (/^https?:\/\//i.test(reference)) return reference;
    return items.find((item) => item.id === reference)?.source_url ?? null;
  };

  const handleVerify = async (claim: InvestmentClaim) => {
    setVerifying((current) => ({ ...current, [claim.id]: true }));
    try {
      await investmentApi.verifyClaim(claim.id);
      message.success("验证完成");
      void load();
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setVerifying((current) => ({ ...current, [claim.id]: false }));
    }
  };

  const handleSetStatus = async (
    claim: InvestmentClaim,
    verificationStatus: VerificationStatus,
    verificationSummary: string,
  ) => {
    setVerifying((current) => ({ ...current, [claim.id]: true }));
    try {
      await investmentApi.setClaimStatus(claim.id, {
        verification_status: verificationStatus,
        verification_summary: verificationSummary,
      });
      message.success("状态已更新");
      void load();
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setVerifying((current) => ({ ...current, [claim.id]: false }));
    }
  };

  const handleLinkThesis = async (claim: InvestmentClaim, thesisId: string) => {
    setVerifying((current) => ({ ...current, [claim.id]: true }));
    try {
      await investmentApi.setClaimStatus(claim.id, {
        verification_status: claim.verification_status,
        thesis_id: thesisId,
      });
      message.success("已关联投资假设");
      void load();
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setVerifying((current) => ({ ...current, [claim.id]: false }));
    }
  };

  return (
    <main className="page">
      <PageHeader
        title="待验证观点"
        description="把观点层信息（YouTube/研报/社媒）转成需要事实证据支撑的待验证观点。"
        extra={<Button type="primary" onClick={() => setOpen(true)}>添加观点</Button>}
      />
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}
      <Card>
        <Spin spinning={loading}>
          {claims.length === 0 ? (
            <Empty description="暂无待验证观点" />
          ) : (
            <List
              dataSource={claims}
              renderItem={(c) => (
                <List.Item
                  actions={[
                    <Button
                      key="verify"
                      size="small"
                      loading={!!verifying[c.id]}
                      onClick={() => void handleVerify(c)}
                    >
                      验证观点
                    </Button>,
                    ...MANUAL_STATUS_ACTIONS.map((action) => (
                      <Button
                        key={action.status}
                        size="small"
                        loading={!!verifying[c.id]}
                        onClick={() => void handleSetStatus(c, action.status, action.summary)}
                      >
                        {action.label}
                      </Button>
                    )),
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <Tag color={VERIF_COLOR[c.verification_status]}>
                          {VERIF_LABEL[c.verification_status]}
                        </Tag>
                        <Tag>{evidenceGroup(c)}</Tag>
                        <Typography.Text>{c.claim_text}</Typography.Text>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={0}>
                        {c.required_evidence?.length > 0 && (
                          <span>需要证据：{c.required_evidence.join("；")}</span>
                        )}
                        {c.verification_summary && <span>{c.verification_summary}</span>}
                        {evidenceReferences(c).length > 0 && (
                          <Space direction="vertical" size={0}>
                            <Typography.Text>证据文档：</Typography.Text>
                            {evidenceReferences(c).map((reference) => {
                              const url = evidenceUrl(reference);
                              return url ? (
                                <Typography.Link
                                  key={reference}
                                  href={url}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  原文证据：{reference}
                                </Typography.Link>
                              ) : (
                                <Typography.Text type="secondary" key={reference}>
                                  原文链接缺失：{reference}
                                </Typography.Text>
                              );
                            })}
                          </Space>
                        )}
                        {linkedOpportunity(c) && (
                          <span>
                            关联机会：{linkedOpportunity(c)?.title}
                          </span>
                        )}
                        {theses.length > 0 && (
                          <Space size={8}>
                            <span>关联假设：</span>
                            <Select
                              aria-label="关联假设"
                              size="small"
                              placeholder="选择假设"
                              value={c.thesis_id ?? undefined}
                              loading={!!verifying[c.id]}
                              style={{ minWidth: 220 }}
                              options={theses.map((t) => ({ value: t.id, label: t.title }))}
                              onChange={(value) => void handleLinkThesis(c, value)}
                            />
                          </Space>
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
        open={open}
        title="添加待验证观点"
        onCancel={() => setOpen(false)}
        onOk={handleCreate}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item label="观点内容" name="claim_text" rules={[{ required: true }]}>
            <Input.TextArea rows={3} placeholder="例如：某公司数据中心收入将翻倍" />
          </Form.Item>
          <Form.Item label="关联观察对象" name="watchlist_id">
            <WatchlistSelector watchlists={watchlists} />
          </Form.Item>
          <Form.Item label="关联投资假设" name="thesis_id">
            <Select
              allowClear
              placeholder="选择假设（可选）"
              options={theses.map((t) => ({ value: t.id, label: t.title }))}
            />
          </Form.Item>
          <Form.Item label="需要验证的事实（每行一条）" name="required_evidence">
            <Input.TextArea rows={3} placeholder={"10-K 分部数据\n财报电话会确认"} />
          </Form.Item>
        </Form>
      </Modal>
    </main>
  );
}
