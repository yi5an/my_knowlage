import { Button, Card, Divider, Space, Tag, Typography } from "antd";
import { Link } from "react-router-dom";

import type {
  AccountRecommendation,
  InvestmentSource,
} from "../../services/investmentApi";

export type RecommendationCardProps = {
  recommendation: AccountRecommendation;
  onFollow: (recommendation: AccountRecommendation) => Promise<InvestmentSource>;
  onPause?: (sourceId: string) => Promise<void>;
  followedSource?: InvestmentSource;
};

const PLATFORM_LABELS: Record<string, string> = {
  x: "X",
  youtube: "YouTube",
  institution: "机构",
  manual: "机构与一手源",
};

function frequencyLabel(seconds: number): string {
  if (seconds >= 86_400 && seconds % 86_400 === 0) return `每 ${seconds / 86_400} 天`;
  if (seconds >= 3_600 && seconds % 3_600 === 0) return `每 ${seconds / 3_600} 小时`;
  if (seconds >= 60 && seconds % 60 === 0) return `每 ${seconds / 60} 分钟`;
  return `每 ${seconds} 秒`;
}

function roleLabel(roleType: string): string {
  const labels: Record<string, string> = {
    analyst: "分析师",
    researcher: "研究者",
    institution: "机构",
    journalist: "记者",
    executive: "企业管理者",
  };
  return labels[roleType] ?? roleType;
}

export function RecommendationCard({
  recommendation,
  onFollow,
  onPause,
  followedSource,
}: RecommendationCardProps) {
  const followed = recommendation.status === "followed" || Boolean(recommendation.source_id);
  const sourceId = recommendation.source_id;
  const platform = recommendation.platform.toLowerCase();
  const impactPersonId = sourceId ?? recommendation.id;

  return (
    <Card className="investment-recommendation-card" size="small">
      <div className="investment-recommendation-card__header">
        <Space wrap size={[6, 6]}>
          <Tag color={platform === "x" ? "#111827" : platform === "youtube" ? "red" : "blue"}>
            {PLATFORM_LABELS[platform] ?? recommendation.platform}
          </Tag>
          <Typography.Text strong>{recommendation.display_name ?? recommendation.handle}</Typography.Text>
          <Typography.Text type="secondary">@{recommendation.handle.replace(/^@/, "")}</Typography.Text>
          <Tag>{roleLabel(recommendation.role_type)}</Tag>
        </Space>
        <Tag color={recommendation.recommendation_label === "样本不足" ? "warning" : "success"}>
          {recommendation.recommendation_label}
        </Tag>
      </div>

      <Typography.Paragraph className="investment-recommendation-card__reason">
        {recommendation.reason}
      </Typography.Paragraph>

      <Space wrap size={[6, 6]} className="investment-recommendation-card__themes">
        {recommendation.theme_ids.length > 0 ? (
          recommendation.theme_ids.map((themeId) => <Tag key={themeId}>主题：{themeId}</Tag>)
        ) : (
          <Typography.Text type="secondary">暂无主题绑定</Typography.Text>
        )}
      </Space>

      <Divider className="investment-recommendation-card__divider" />
      <div className="investment-recommendation-card__meta">
        <span>事件样本 {recommendation.sample_count}</span>
        <span>证据 {recommendation.evidence_count}</span>
        <span>追踪频率：{frequencyLabel(followedSource?.poll_interval_seconds ?? 900)}</span>
      </div>

      <div className="investment-recommendation-card__actions">
        {followed ? (
          <Space wrap>
            <Button size="small" type="primary" disabled>
              已关注
            </Button>
            <Button
              size="small"
              disabled={!sourceId || !onPause}
              onClick={() => {
                if (sourceId && onPause) void onPause(sourceId);
              }}
            >
              暂停追踪
            </Button>
            {sourceId && (
              <Link to={`/investment/items?source_id=${encodeURIComponent(sourceId)}`}>
                <Button size="small">查看最近内容</Button>
              </Link>
            )}
            <Link to={`/investment/person-sources/${encodeURIComponent(impactPersonId)}/impact`}>
              <Button size="small">查看人物影响</Button>
            </Link>
          </Space>
        ) : (
          <Button
            type="primary"
            onClick={() => void onFollow(recommendation)}
            aria-label="+ 关注追踪"
          >
            + 关注追踪
          </Button>
        )}
      </div>
    </Card>
  );
}
