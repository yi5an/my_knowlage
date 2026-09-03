const ITEMS = [
  ["confirmed", "已确认"],
  ["inference", "待审核 / AI 推断"],
  ["conflict", "反驳 / 冲突"],
  ["qualified", "限定条件"],
  ["stale", "证据过期"],
] as const;

export function GraphLegend() {
  return (
    <section className="provenance-legend" aria-label="图例">
      <strong>图例</strong>
      <ul>
        {ITEMS.map(([kind, label]) => (
          <li key={kind}>
            <span className={`provenance-legend__swatch provenance-legend__swatch--${kind}`} />
            {label}
          </li>
        ))}
      </ul>
    </section>
  );
}
