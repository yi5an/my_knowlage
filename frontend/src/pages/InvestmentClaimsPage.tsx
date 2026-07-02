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
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { WatchlistSelector } from "../components/investment/WatchlistSelector";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type InvestmentClaim,
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
};

const VERIF_COLOR: Record<VerificationStatus, string> = {
  pending: "warning",
  verifying: "processing",
  verified: "success",
  refuted: "error",
  local_only: "default",
};

export function InvestmentClaimsPage() {
  const [claims, setClaims] = useState<InvestmentClaim[]>([]);
  const [watchlists, setWatchlists] = useState<InvestmentWatchlist[]>([]);
  const [theses, setTheses] = useState<InvestmentThesis[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, w, t] = await Promise.all([
        investmentApi.listClaims(),
        investmentApi.listWatchlist(),
        investmentApi.listTheses(),
      ]);
      setClaims(c);
      setWatchlists(w);
      setTheses(t);
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
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space>
                        <Tag color={VERIF_COLOR[c.verification_status]}>
                          {VERIF_LABEL[c.verification_status]}
                        </Tag>
                        <Typography.Text>{c.claim_text}</Typography.Text>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={0}>
                        {c.required_evidence?.length > 0 && (
                          <span>需要证据：{c.required_evidence.join("；")}</span>
                        )}
                        {c.verification_summary && <span>{c.verification_summary}</span>}
                        {c.evidence_doc_ids?.length > 0 && (
                          <span>证据文档：{c.evidence_doc_ids.length} 篇</span>
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
