import type { Totals } from "../api/types";
import { count, money, percent, rate } from "../lib/format";

// Always rendered from the API's own totals, never summed from the rows on screen: the table
// shows one page of groups, and a bar that disagreed with it would be worse than no bar.
export function TotalsBar({ totals }: { totals: Totals | null }) {
  const tiles: [string, string][] = totals
    ? [
        ["campaign-days", count(totals.rows)],
        ["spend", money(totals.spend_usd)],
        ["impressions", count(totals.impressions)],
        ["clicks", count(totals.clicks)],
        ["CTR", percent(totals.ctr)],
        ["CPC", rate(totals.cpc)],
      ]
    : [];

  return (
    <div className="totals" aria-live="polite">
      {tiles.map(([label, value]) => (
        <div className="tile" key={label}>
          <span className="tile-label">{label}</span>
          <span className="tile-value">{value}</span>
        </div>
      ))}
    </div>
  );
}
