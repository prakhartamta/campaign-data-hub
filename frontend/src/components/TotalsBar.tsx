import type { Totals } from "../api/types";
import { count, money, percent, rate } from "../lib/format";

const LABELS = ["campaign-days", "spend", "impressions", "clicks", "CTR", "CPC"];

// Always rendered from the API's own totals, never summed from the rows on screen: the table
// shows one page of groups, and a bar that disagreed with it would be worse than no bar.
export function TotalsBar({ totals, loading = false }: { totals: Totals | null; loading?: boolean }) {
  // While an answer is on its way, on a first load or during a run, the six cards stay and only
  // their numbers give way to bars, so the page does not reflow when the numbers land.
  if (loading) {
    return (
      <div className="totals" aria-live="polite" aria-busy="true">
        {LABELS.map((label) => (
          <div className="tile" key={label}>
            <span className="tile-label cap">{label}</span>
            <span className="tile-value is-skeleton">
              <span className="skeleton" />
            </span>
          </div>
        ))}
      </div>
    );
  }

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
          <span className="tile-label cap">{label}</span>
          <span className="tile-value">{value}</span>
        </div>
      ))}
    </div>
  );
}
