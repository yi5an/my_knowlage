import { Select } from "antd";
import type { InvestmentWatchlist } from "../../services/investmentApi";

/** Single-select watchlist picker for item/claim/thesis forms. */
export function WatchlistSelector({
  watchlists,
  value,
  onChange,
}: {
  watchlists: InvestmentWatchlist[];
  value?: string;
  onChange?: (id: string | undefined) => void;
}) {
  return (
    <Select
      allowClear
      placeholder="选择观察对象（可选）"
      value={value}
      onChange={onChange}
      style={{ width: "100%" }}
      options={watchlists.map((w) => ({
        value: w.id,
        label: w.ticker ? `${w.name} (${w.ticker})` : w.name,
      }))}
    />
  );
}
