import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Button, Empty, Select, Space, Spin, Tag, Typography, message } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

import {
  getYouTubeTimeline,
  retryVideo,
  youtubeThumbnailUrl,
  type TimelineChannel,
  type TimelineItem,
  type TimelinePage,
} from "../../services/youtubeApi";

const { Text, Paragraph } = Typography;
const ALL = "";
const UNKNOWN_CHANNEL_ID = "__unknown__";

const shellStyle: CSSProperties = {
  overflow: "auto",
  maxHeight: "70vh",
  border: "1px solid #f0f0f0",
  borderRadius: 8,
  background: "#f8fafc",
};

const dateStyle: CSSProperties = {
  position: "sticky",
  left: 0,
  zIndex: 2,
  padding: "12px 10px",
  background: "#fff",
  borderRight: "1px solid #e5e7eb",
  borderBottom: "1px solid #eef0f3",
  color: "#667085",
  fontSize: 12,
};

const laneHeaderStyle: CSSProperties = {
  position: "sticky",
  top: 0,
  zIndex: 1,
  height: 45,
  padding: "13px 12px",
  background: "#fff",
  borderRight: "1px solid #e5e7eb",
  borderBottom: "1px solid #e5e7eb",
  fontWeight: 600,
};

const rowStyle: CSSProperties = {
  minHeight: 150,
  padding: 12,
  borderRight: "1px solid #e5e7eb",
  borderBottom: "1px solid #eef0f3",
};

const cardStyle: CSSProperties = {
  background: "#fff",
  borderRadius: 7,
  padding: 9,
  boxShadow: "0 1px 3px rgba(16,24,40,.08)",
  overflow: "hidden",
};

function statusLabel(item: TimelineItem): { text: string; color: string } {
  if (item.summary_status === "access_denied") return { text: "无访问权限", color: "default" };
  if (item.summary_status === "completed") return { text: "已完成", color: "green" };
  if (item.failure_stage === "transcript" || item.summary_status === "no_transcript") {
    return { text: "转写失败", color: "red" };
  }
  if (item.failure_stage === "capture") return { text: "采集失败", color: "red" };
  if (item.failure_stage === "summary") return { text: "总结失败", color: "red" };
  if (item.summary_status === "failed") return { text: "处理失败", color: "red" };
  return { text: "处理中", color: "gold" };
}

function effectiveDate(item: TimelineItem): string {
  const date = dateKey(item);
  return item.time_source === "created_at" ? `${date} · 平台时间` : date;
}

function dateKey(item: TimelineItem): string {
  return item.effective_time.slice(0, 10);
}

function channelKey(channel: Pick<TimelineChannel, "channel_id">): string {
  return channel.channel_id ?? UNKNOWN_CHANNEL_ID;
}

export interface YouTubeTimelineProps {
  workspaceId?: string;
}

export function YouTubeTimeline({ workspaceId = "ws_default" }: YouTubeTimelineProps) {
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [channels, setChannels] = useState<TimelineChannel[]>([]);
  const [months, setMonths] = useState<TimelinePage["months"]>([]);
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selectedChannel, setSelectedChannel] = useState(ALL);
  const [selectedStatus, setSelectedStatus] = useState(ALL);
  const [selectedMonth, setSelectedMonth] = useState(ALL);
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<Record<string, boolean>>({});
  const [scrollRoot, setScrollRoot] = useState<HTMLDivElement | null>(null);
  const [sentinelNode, setSentinelNode] = useState<HTMLDivElement | null>(null);
  const requestRef = useRef(0);

  const loadPage = useCallback(async (cursor: string | null, replace: boolean) => {
    const requestId = ++requestRef.current;
    if (replace) setLoading(true);
    else setLoadingMore(true);
    setError(null);
    try {
      const page = await getYouTubeTimeline({
        workspaceId,
        limit: 50,
        cursor,
        channelId: selectedChannel || null,
        status: selectedStatus || null,
        yearMonth: selectedMonth || null,
      });
      if (requestId !== requestRef.current) return;
      setItems((current) => {
        const incoming = replace ? page.items : [...current, ...page.items];
        const seen = new Set<string>();
        return incoming.filter((item) => !seen.has(item.video_id) && seen.add(item.video_id));
      });
      setChannels(page.channels);
      setMonths(page.months);
      setStatusCounts(page.status_counts);
      setNextCursor(page.next_cursor);
    } catch (cause) {
      if (requestId === requestRef.current) setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (requestId === requestRef.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [selectedChannel, selectedMonth, selectedStatus, workspaceId]);

  useEffect(() => {
    setItems([]);
    setNextCursor(null);
    void loadPage(null, true);
  }, [loadPage]);

  useEffect(() => {
    const refresh = () => void loadPage(null, true);
    window.addEventListener("youtube-timeline-refresh", refresh);
    return () => window.removeEventListener("youtube-timeline-refresh", refresh);
  }, [loadPage]);

  useEffect(() => {
    if (!sentinelNode || !scrollRoot || !nextCursor || loading || loadingMore) return;
    const observer = new window.IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadPage(nextCursor, false);
    }, { root: scrollRoot, rootMargin: "0px 0px 120px 0px" });
    observer.observe(sentinelNode);
    return () => observer.disconnect();
  }, [loadPage, loading, loadingMore, nextCursor, scrollRoot, sentinelNode]);

  const visibleChannels = useMemo(() => {
    if (showAll) return channels;
    if (selectedChannel) {
      return channels.filter((channel) => channelKey(channel) === selectedChannel);
    }
    if (selectedStatus || selectedMonth) {
      const activeChannels = new Set(items.map((item) => channelKey(item)));
      return channels.filter((channel) => activeChannels.has(channelKey(channel)));
    }
    return channels.slice(0, 6);
  }, [channels, items, selectedChannel, selectedMonth, selectedStatus, showAll]);
  const grouped = useMemo(() => {
    const byDate = new Map<string, Map<string, TimelineItem[]>>();
    for (const item of items) {
      const byChannel = byDate.get(dateKey(item)) ?? new Map<string, TimelineItem[]>();
      const key = channelKey(item);
      const list = byChannel.get(key) ?? [];
      list.push(item);
      byChannel.set(key, list);
      byDate.set(dateKey(item), byChannel);
    }
    return Array.from(byDate.entries()).sort(([a], [b]) => b.localeCompare(a));
  }, [items]);

  async function handleRetry(item: TimelineItem) {
    setRetrying((current) => ({ ...current, [item.video_id]: true }));
    try {
      await retryVideo(item.video_id, workspaceId);
      message.success("已重新提交，后台处理中");
      await loadPage(null, true);
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setRetrying((current) => ({ ...current, [item.video_id]: false }));
    }
  }

  const channelOptions = channels.map((channel) => ({
    label: channel.channel_name,
    value: channelKey(channel),
  }));
  const gridTemplateColumns = `92px repeat(${visibleChannels.length}, 250px)`;
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Space wrap>
        <Select
          aria-label="博主筛选"
          value={selectedChannel}
          onChange={setSelectedChannel}
          style={{ minWidth: 180 }}
          options={[{ label: "全部博主", value: ALL }, ...channelOptions]}
        />
        <Select
          aria-label="状态筛选"
          value={selectedStatus}
          onChange={setSelectedStatus}
          style={{ minWidth: 130 }}
          options={[
            { label: `全部状态 (${Object.values(statusCounts).reduce((a, b) => a + b, 0)})`, value: ALL },
            { label: "已完成", value: "completed" },
            { label: "处理中", value: "processing" },
            { label: "失败", value: "failed" },
            { label: "无字幕", value: "no_transcript" },
            { label: "无访问权限", value: "access_denied" },
          ]}
        />
        <Select
          aria-label="月份跳转"
          value={selectedMonth}
          onChange={setSelectedMonth}
          style={{ minWidth: 140 }}
          options={[{ label: "全部月份", value: ALL }, ...months.map((month) => ({ label: `${month.year_month} (${month.item_count})`, value: month.year_month }))]}
        />
        <Button onClick={() => setShowAll((current) => !current)}>
          {showAll ? "收起博主" : "显示全部博主"}
        </Button>
        <Text type="secondary">共 {items.length}{nextCursor ? "+" : ""} 条</Text>
      </Space>

      {error && (
        <Space>
          <Text type="danger">时间轴加载失败：{error}</Text>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => void loadPage(null, true)}>重试</Button>
        </Space>
      )}
      {loading && items.length === 0 ? <Spin /> : items.length === 0 ? <Empty description="暂无 YouTube 采集记录" /> : (
        <div
          ref={setScrollRoot}
          data-testid="youtube-timeline-scroll"
          style={shellStyle}
        >
          <div
            data-testid="youtube-timeline-grid"
            style={{
              display: "grid",
              gridTemplateColumns,
              minWidth: 92 + visibleChannels.length * 250,
            }}
          >
            <div style={{ ...dateStyle, top: 0, zIndex: 3, height: 45 }}>日期</div>
            {visibleChannels.map((channel) => (
              <div key={channelKey(channel)} style={laneHeaderStyle}>
                {channel.channel_name}
                <Text type="secondary" style={{ float: "right", fontSize: 12 }}>
                  {channel.item_count}
                </Text>
              </div>
            ))}
            {grouped.flatMap(([date, byChannel]) => [
              <div key={`${date}:date`} style={dateStyle}>{date}</div>,
              ...visibleChannels.map((channel) => (
                <div key={`${date}:${channelKey(channel)}`} style={rowStyle}>
                    {(byChannel.get(channelKey(channel)) ?? []).map((item) => {
                      const status = statusLabel(item);
                      const body = <>
                        {item.thumbnail_url && (
                          <img
                            src={youtubeThumbnailUrl(item.video_id) ?? undefined}
                            alt=""
                            loading="lazy"
                            style={{ width: "100%", height: 104, objectFit: "cover", borderRadius: 5, marginBottom: 6 }}
                            onError={(event) => { event.currentTarget.style.display = "none"; }}
                          />
                        )}
                        <Text strong ellipsis={{ tooltip: item.title }} style={{ display: "block" }}>{item.title}</Text>
                        <Space size={4}>
                          <Text type="secondary" style={{ fontSize: 12 }}>{effectiveDate(item)}</Text>
                          <Tag color={status.color}>{status.text}</Tag>
                        </Space>
                        {item.tldr && <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ margin: "5px 0 0", fontSize: 12 }}>{item.tldr}</Paragraph>}
                        {item.error && <Paragraph type="danger" ellipsis={{ rows: 2 }} style={{ margin: "5px 0 0", fontSize: 12 }}>{item.error}</Paragraph>}
                        <Space wrap size={[2, 2]} style={{ marginTop: 4 }}>{item.tags.slice(0, 3).map((tag) => <Tag key={tag}>#{tag}</Tag>)}</Space>
                        {item.retryable && <Button size="small" type="link" loading={retrying[item.video_id]} onClick={() => void handleRetry(item)} style={{ padding: 0, height: 22 }}>重新处理</Button>}
                      </>;
                      return <div key={item.video_id} style={{ ...cardStyle, marginBottom: 8, borderLeft: `3px solid ${status.color === "green" ? "#52c41a" : status.color === "red" ? "#ff4d4f" : status.color === "default" ? "#8c8c8c" : "#faad14"}` }}>
                        {item.summary_status === "completed" && item.document_id ? <Link to={`/youtube/summary/${item.document_id}`}>{body}</Link> : body}
                      </div>;
                    })}
                </div>
              )),
            ])}
          </div>
          <div data-testid="youtube-timeline-sentinel" ref={setSentinelNode} style={{ height: 1 }} />
        </div>
      )}
      {loadingMore && <Spin size="small" tip="加载更早历史…" />}
      {showAll && visibleChannels.length < channels.length && <Text type="secondary">已展开全部 {visibleChannels.length} 位博主</Text>}
    </Space>
  );
}
