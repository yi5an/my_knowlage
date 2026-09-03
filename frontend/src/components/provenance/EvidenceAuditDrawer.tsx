import { useEffect, useState } from "react";

import { ApiError } from "../../services/client";
import type { ReviewAction, TraceEdgeDetail } from "../../types/provenance";
import { EvidenceLocatorLink } from "./EvidenceLocatorLink";

interface EvidenceAuditDrawerProps {
  open: boolean;
  edge: TraceEdgeDetail | null;
  onClose: () => void;
  onReview: (action: ReviewAction, version: number, note: string) => Promise<unknown> | unknown;
  onReload?: () => Promise<unknown> | unknown;
}

const ACTIONS: Array<[ReviewAction, string]> = [
  ["confirm", "确认关系"],
  ["reject", "拒绝关系"],
  ["mark_conflict", "标记冲突"],
  ["reset_pending", "重置待审"],
];

export function EvidenceAuditDrawer({
  open,
  edge,
  onClose,
  onReview,
  onReload,
}: EvidenceAuditDrawerProps) {
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [conflict, setConflict] = useState(false);

  useEffect(() => {
    setConflict(false);
  }, [edge?.id, edge?.version_no]);

  if (!open) return null;
  if (!edge) {
    return (
      <aside className="provenance-audit-drawer" aria-label="关系审计">
        <button type="button" onClick={onClose} aria-label="关闭审计">
          ×
        </button>
        <p>正在加载关系审计记录…</p>
      </aside>
    );
  }

  const review = async (action: ReviewAction) => {
    setSubmitting(true);
    setConflict(false);
    try {
      await onReview(action, edge.version_no, note);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setConflict(true);
        await onReload?.();
      } else {
        throw error;
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <aside className="provenance-audit-drawer" aria-label="关系审计">
      <header>
        <div>
          <small>关系审计 · v{edge.version_no}</small>
          <h2>{edge.relation_type}</h2>
        </div>
        <button type="button" onClick={onClose} aria-label="关闭审计">
          ×
        </button>
      </header>
      {conflict ? (
        <div role="alert" className="provenance-audit-conflict">
          这条关系已有更新版本，已重新加载；你的审核备注仍保留。
        </div>
      ) : null}
      <dl className="provenance-audit-meta">
        <div>
          <dt>推理说明</dt>
          <dd>{edge.rationale ?? "未提供"}</dd>
        </div>
        <div>
          <dt>置信度</dt>
          <dd>{edge.confidence === null ? "未知" : `${Math.round(edge.confidence * 100)}%`}</dd>
        </div>
        <div>
          <dt>状态</dt>
          <dd>{edge.review_status} / {edge.validation_status}</dd>
        </div>
        <div>
          <dt>模型 / Prompt</dt>
          <dd>{String(edge.model_metadata.model ?? "未知")} / {String(edge.model_metadata.prompt_version ?? "未知")}</dd>
        </div>
      </dl>
      <section>
        <h3>原始证据</h3>
        <div className="provenance-evidence-list">
          {edge.evidence.map((anchor) => (
            <article key={anchor.id} className="provenance-evidence-card">
              <div>
                <span>{anchor.anchor_type}</span>
                {anchor.validation_state === "stale" ? <strong>证据已过期</strong> : null}
              </div>
              <blockquote>{anchor.quote}</blockquote>
              <small>
                来源质量：{anchor.source_quality === null ? "未知" : `${Math.round(anchor.source_quality * 100)}%`}
              </small>
              <EvidenceLocatorLink anchor={anchor} />
            </article>
          ))}
        </div>
      </section>
      <section>
        <h3>审核历史</h3>
        <pre>{JSON.stringify(edge.review_history, null, 2)}</pre>
      </section>
      <label>
        审核备注
        <textarea
          aria-label="审核备注"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          rows={3}
        />
      </label>
      <div className="provenance-audit-actions">
        {ACTIONS.map(([action, label]) => (
          <button
            key={action}
            type="button"
            disabled={submitting}
            onClick={() => void review(action)}
          >
            {label}
          </button>
        ))}
      </div>
    </aside>
  );
}
