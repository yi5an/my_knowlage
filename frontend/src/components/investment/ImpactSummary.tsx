import { Card, Col, Progress, Row, Statistic, Tag, Typography } from "antd";

import type { PersonImpactProfile } from "../../services/investmentApi";

export type ImpactSummaryProps = {
  profile: PersonImpactProfile;
};

function percent(value?: number | null, digits = 1): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function hours(value?: number | null): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(1)} 小时`;
}

export function ImpactSummary({ profile }: ImpactSummaryProps) {
  const notAttributable = profile.uncertainty?.includes("不可归因") ?? false;
  const attributable = profile.sample_sufficient && profile.valid_sample_count > 0 && !notAttributable;
  const totalEvents = profile.positive_event_count + profile.negative_event_count + profile.neutral_event_count;
  const positiveShare = totalEvents > 0 ? (profile.positive_event_count / totalEvents) * 100 : 0;

  return (
    <Card className="investment-impact-summary" title="人物影响概览">
      <SpaceSummaryHeader
        profile={profile}
        attributable={attributable}
        notAttributable={notAttributable}
      />
      <Row gutter={[12, 12]}>
        <Col xs={12} sm={6}>
          <Statistic title="有效样本" value={profile.valid_sample_count} suffix={`/ ${profile.sample_count}`} />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic title="平均提前量" value={hours(profile.average_lead_time_hours)} />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic title="平均超额收益（1D）" value={percent(profile.average_excess_return_1d)} />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic title="稳定性" value={percent(profile.stability_score)} />
        </Col>
      </Row>

      <div className="investment-impact-summary__distribution" aria-label="事件方向分布">
        <div className="investment-impact-summary__distribution-labels">
          <span>正向 {profile.positive_event_count}</span>
          <span>中性 {profile.neutral_event_count}</span>
          <span>负向 {profile.negative_event_count}</span>
        </div>
        <Progress
          percent={100}
          success={{ percent: positiveShare, strokeColor: "#3f9b5f" }}
          strokeColor="#d16b56"
          trailColor="#c3c9d1"
          showInfo={false}
        />
        <Typography.Text type="secondary">
          方向分布仅描述历史关联，不代表因果关系或未来收益。
        </Typography.Text>
      </div>
    </Card>
  );
}

function SpaceSummaryHeader({
  profile,
  attributable,
  notAttributable,
}: {
  profile: PersonImpactProfile;
  attributable: boolean;
  notAttributable: boolean;
}) {
    return (
    <div className="investment-impact-summary__status">
      <Tag color={attributable ? "success" : "warning"}>
        {attributable ? "样本充分" : notAttributable ? "不可归因" : "样本不足"}
      </Tag>
      {profile.uncertainty && <Typography.Text type="secondary">{profile.uncertainty}</Typography.Text>}
      {!attributable && !notAttributable && (
        <Typography.Text type="warning">
          当前不下影响结论；需积累至少 5 个有效事件样本。
        </Typography.Text>
      )}
    </div>
  );
}
