import { useMemo } from "react";
import { Avatar, Empty, Input, List, Tag, Typography } from "antd";

import { nodeImageUrl, nodeZhName, type GraphNode } from "../services/graphApi";

const { Text } = Typography;

const TYPE_ORDER = [
  "organization",
  "company",
  "person",
  "technology",
  "concept",
  "financial_metric",
  "entity",
];

const TYPE_LABEL: Record<string, string> = {
  organization: "公司",
  company: "公司",
  person: "人物",
  technology: "技术",
  concept: "概念",
  financial_metric: "财务",
  entity: "实体",
};

const TYPE_COLOR: Record<string, string> = {
  organization: "#722ed1",
  company: "#722ed1",
  person: "#eb2f96",
  technology: "#52c41a",
  concept: "#fa8c16",
  financial_metric: "#faad14",
  entity: "#1677ff",
};

export interface EntityNodeListProps {
  nodes: GraphNode[];
  selectedId?: string | null;
  filter: string;
  onFilterChange: (v: string) => void;
  onSelect?: (node: GraphNode) => void;
}

/**
 * Left-side entity list, grouped by type and sorted by name within each group.
 * Clicking an item selects + focuses the node in the graph.
 */
export function EntityNodeList({
  nodes,
  selectedId,
  filter,
  onFilterChange,
  onSelect,
}: EntityNodeListProps) {
  const groups = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const filtered = f
      ? nodes.filter((n) => {
          const zh = nodeZhName(n) ?? "";
          return (
            n.label.toLowerCase().includes(f) || zh.toLowerCase().includes(f)
          );
        })
      : nodes;
    const byType = new Map<string, GraphNode[]>();
    for (const n of filtered) {
      const list = byType.get(n.node_type) ?? [];
      list.push(n);
      byType.set(n.node_type, list);
    }
    const sortedTypes = [...byType.keys()].sort(
      (a, b) =>
        (TYPE_ORDER.indexOf(a) === -1 ? 99 : TYPE_ORDER.indexOf(a)) -
        (TYPE_ORDER.indexOf(b) === -1 ? 99 : TYPE_ORDER.indexOf(b)),
    );
    return sortedTypes.map((type) => ({
      type,
      items: byType.get(type)!.sort((a, b) => a.label.localeCompare(b.label)),
    }));
  }, [nodes, filter]);

  return (
    <>
      <Input.Search
        placeholder="筛选实体..."
        value={filter}
        onChange={(e) => onFilterChange(e.target.value)}
        size="small"
        style={{ marginBottom: 8 }}
      />
      {groups.length === 0 ? (
        <Empty description="无匹配实体" />
      ) : (
        groups.map((group) => (
          <div key={group.type} style={{ marginBottom: 12 }}>
            <div style={{ marginBottom: 4 }}>
              <Tag color={TYPE_COLOR[group.type] ?? "#1677ff"}>
                {TYPE_LABEL[group.type] ?? group.type} · {group.items.length}
              </Tag>
            </div>
            <List
              size="small"
              split={false}
              dataSource={group.items}
              renderItem={(node) => {
                const img = nodeImageUrl(node);
                const zh = nodeZhName(node);
                const active = node.id === selectedId;
                return (
                  <List.Item
                    style={{
                      cursor: "pointer",
                      padding: "4px 8px",
                      borderRadius: 4,
                      background: active ? "#e6f4ff" : "transparent",
                    }}
                    onClick={() => onSelect?.(node)}
                  >
                    <List.Item.Meta
                      avatar={
                        img ? (
                          <Avatar size={24} src={img} />
                        ) : (
                          <Avatar
                            size={24}
                            style={{
                              background: TYPE_COLOR[node.node_type] ?? "#1677ff",
                              fontSize: 12,
                            }}
                          >
                            {(node.label[0] ?? "?").toUpperCase()}
                          </Avatar>
                        )
                      }
                      title={
                        <Text strong={active} style={{ fontSize: 13 }}>
                          {zh ?? node.label}
                        </Text>
                      }
                      description={
                        zh ? (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {node.label}
                          </Text>
                        ) : null
                      }
                    />
                  </List.Item>
                );
              }}
            />
          </div>
        ))
      )}
    </>
  );
}
