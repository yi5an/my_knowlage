import { Alert, Button, Empty, Skeleton, Space, Tabs, Typography, message } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { RecommendationCard } from "../components/investment/RecommendationCard";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../services/client";
import {
  investmentApi,
  type AccountRecommendation,
  type InvestmentSource,
} from "../services/investmentApi";

type PlatformTab = "all" | "x" | "youtube" | "institution";

const TAB_ITEMS: Array<{ key: PlatformTab; label: string }> = [
  { key: "all", label: "全部推荐" },
  { key: "x", label: "X 人物" },
  { key: "youtube", label: "YouTube 频道" },
  { key: "institution", label: "机构与一手源" },
];

function displayError(error: unknown): string {
  return error instanceof ApiError ? error.message : String(error);
}

export function AccountDiscoveryPage() {
  const [recommendations, setRecommendations] = useState<AccountRecommendation[]>([]);
  const [followedSources, setFollowedSources] = useState<Record<string, InvestmentSource>>({});
  const [activeTab, setActiveTab] = useState<PlatformTab>("all");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchNotice, setSearchNotice] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await investmentApi.listAccountRecommendations();
      setRecommendations(rows);
      setSearchNotice(rows.some((row) => row.reason.includes("搜索服务未配置")));
      setFollowedSources((current) => {
        const next = { ...current };
        rows.forEach((row) => {
          if (row.source_id && row.status === "followed" && !next[row.id]) {
            next[row.id] = {
              id: row.source_id,
              workspace_id: row.workspace_id,
              source_type: row.platform === "youtube" ? "rss" : "x_web",
              name: row.display_name ?? row.handle,
              config: { username: row.handle },
              default_info_layer: "opinion",
              default_watchlist_ids: [],
              poll_interval_seconds: 900,
              enabled: true,
            };
          }
        });
        return next;
      });
    } catch (e) {
      const detail = displayError(e);
      setError(detail);
      setSearchNotice(detail.includes("搜索服务未配置"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const rows = await investmentApi.refreshAccountRecommendations();
      setRecommendations(rows);
      setSearchNotice(rows.some((row) => row.reason.includes("搜索服务未配置")));
      message.success("账号推荐已刷新");
    } catch (e) {
      const detail = displayError(e);
      setError(detail);
      setSearchNotice(detail.includes("搜索服务未配置"));
    } finally {
      setRefreshing(false);
    }
  };

  const visibleRecommendations = useMemo(
    () =>
      activeTab === "all"
        ? recommendations
        : recommendations.filter((row) => row.platform.toLowerCase() === activeTab),
    [activeTab, recommendations],
  );

  const follow = async (recommendation: AccountRecommendation) => {
    try {
      const source = await investmentApi.followAccountRecommendation(recommendation.id);
      setFollowedSources((current) => ({ ...current, [recommendation.id]: source }));
      setRecommendations((rows) =>
        rows.map((row) =>
          row.id === recommendation.id ? { ...row, status: "followed", source_id: source.id } : row,
        ),
      );
      message.success(`已开始追踪 ${recommendation.display_name ?? recommendation.handle}`);
      return source;
    } catch (e) {
      message.error(displayError(e));
      throw e;
    }
  };

  const pause = async (sourceId: string) => {
    try {
      const source = await investmentApi.updateSource(sourceId, { enabled: false });
      setFollowedSources((current) => {
        const next = { ...current };
        const recommendationId = Object.keys(next).find((id) => next[id].id === sourceId);
        if (recommendationId) next[recommendationId] = source;
        return next;
      });
      message.success("追踪已暂停；历史证据仍会保留");
    } catch (e) {
      message.error(displayError(e));
    }
  };

  return (
    <main className="page investment-account-discovery-page">
      <PageHeader
        title="账号发现"
        description="系统从已验证的 X、YouTube 和机构来源中筛选值得学习与追踪的账号，并说明每个推荐的证据基础。"
        extra={
          <Space>
            <Link to="/investment/sources">
              <Button>管理数据源</Button>
            </Link>
            <Button type="primary" loading={refreshing} onClick={() => void refresh()}>
              刷新推荐
            </Button>
          </Space>
        }
      />

      {searchNotice && (
        <Alert
          type="warning"
          showIcon
          message="搜索服务未配置"
          description="当前只展示工作区内已有的账号与证据；配置搜索服务后才会扩展外部候选。"
          style={{ marginBottom: 16 }}
        />
      )}
      {error && !searchNotice && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as PlatformTab)}
        items={TAB_ITEMS.map((tab) => ({ key: tab.key, label: tab.label }))}
      />

      <Skeleton loading={loading} active>
        {visibleRecommendations.length === 0 ? (
          <Empty description="暂无符合条件的账号推荐。先刷新推荐或配置一个真实数据源。" />
        ) : (
          <div className="investment-recommendation-grid">
            {visibleRecommendations.map((recommendation) => (
              <RecommendationCard
                key={recommendation.id}
                recommendation={{
                  ...recommendation,
                  source_id: followedSources[recommendation.id]?.id ?? recommendation.source_id,
                }}
                onFollow={follow}
                onPause={pause}
                followedSource={followedSources[recommendation.id]}
              />
            ))}
          </div>
        )}
      </Skeleton>

      <Typography.Paragraph type="secondary" className="investment-account-discovery-page__note">
        关注追踪是 KnowPilot 内部订阅，不会改变你在 X 或 YouTube 上的外部关注关系。
      </Typography.Paragraph>
    </main>
  );
}
