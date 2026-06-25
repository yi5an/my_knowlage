/**
 * Relation-type English -> Chinese label mapping.
 *
 * Extraction used to emit free-form English relation types (competes_with,
 * transforms, ...). New extractions emit Chinese types directly, but older
 * data still has English. This maps both to a consistent Chinese display.
 * Unknown types fall back to the original string.
 */
const RELATION_ZH: Record<string, string> = {
  // 竞合
  competes_with: "竞争",
  competes: "竞争",
  合作: "合作",
  cooperates_with: "合作",
  partners_with: "合作",
  // 产业链
  供应: "供应",
  supplies: "供应",
  上游: "上游",
  upstream_of: "上游",
  下游: "下游",
  downstream_of: "下游",
  // 资本
  投资: "投资",
  invests_in: "投资",
  收购: "收购",
  acquires: "收购",
  acquired: "收购",
  // 技术与需求
  依赖: "依赖",
  requires: "依赖",
  depends_on: "依赖",
  驱动: "驱动",
  drives: "驱动",
  drives_demand_for: "驱动需求",
  transforms: "变革",
  leads: "领先",
  uses: "使用",
  研发: "研发",
  develops: "研发",
  // 结构
  隶属: "隶属",
  part_of: "隶属",
  belongs_to: "隶属",
  // 其他
  mentions: "提及",
  founded: "创立",
};

export function relationLabel(type: string): string {
  return RELATION_ZH[type] ?? type;
}
