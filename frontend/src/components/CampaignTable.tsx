import type { SummaryGroup } from "../api/types";
import { count, money, percent, rate, sortable } from "../lib/format";

export type SortKey =
  | "campaign"
  | "platform"
  | "rows"
  | "spend_usd"
  | "impressions"
  | "clicks"
  | "ctr"
  | "cpc";

export type SortDirection = "asc" | "desc";

interface Props {
  groups: SummaryGroup[];
  sort: SortKey;
  direction: SortDirection;
  onSort: (key: SortKey) => void;
}

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: "platform", label: "platform", numeric: false },
  { key: "campaign", label: "campaign", numeric: false },
  { key: "rows", label: "days", numeric: true },
  { key: "spend_usd", label: "spend", numeric: true },
  { key: "impressions", label: "impressions", numeric: true },
  { key: "clicks", label: "clicks", numeric: true },
  { key: "ctr", label: "CTR", numeric: true },
  { key: "cpc", label: "CPC", numeric: true },
];

/**
 * Sorted here rather than by the API: this is thirteen rows, and a round trip per column click
 * would be slower than the comparison and would lose the scroll position.
 *
 * Money and the ratios arrive as decimal strings, so they must be parsed to compare. Sorting
 * them as text would rank "9.50" above "48709.02".
 */
export function sortGroups(
  groups: SummaryGroup[],
  key: SortKey,
  direction: SortDirection,
): SummaryGroup[] {
  const sign = direction === "asc" ? 1 : -1;
  return [...groups].sort((left, right) => {
    let order: number;
    if (key === "campaign") {
      // The campaign name is the group's `key`, since the same shape also serves platform groups.
      order = left.key.localeCompare(right.key);
    } else if (key === "platform") {
      order = left.platform.localeCompare(right.platform);
    } else if (key === "rows" || key === "impressions" || key === "clicks") {
      order = left[key] - right[key];
    } else {
      order = sortable(left[key]) - sortable(right[key]);
    }
    // Campaign name breaks every tie, unsigned, so the order is total and two rows that compare
    // equal never swap between renders.
    if (order === 0) return left.key.localeCompare(right.key);
    return order * sign;
  });
}

export function CampaignTable({ groups, sort, direction, onSort }: Props) {
  const rows = sortGroups(groups, sort, direction);

  return (
    <table className="grid-table">
      <thead>
        <tr>
          {COLUMNS.map((column) => (
            <th
              key={column.key}
              className={column.numeric ? "numeric" : undefined}
              aria-sort={
                sort === column.key ? (direction === "asc" ? "ascending" : "descending") : "none"
              }
            >
              <button type="button" onClick={() => onSort(column.key)}>
                {column.label}
                {sort === column.key ? (direction === "asc" ? " ↑" : " ↓") : ""}
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((group) => (
          <tr key={`${group.platform}|${group.key}`}>
            <td>{group.platform}</td>
            <td>{group.key}</td>
            <td className="numeric">{count(group.rows)}</td>
            <td className="numeric">{money(group.spend_usd)}</td>
            <td className="numeric">{count(group.impressions)}</td>
            <td className="numeric">{count(group.clicks)}</td>
            <td className="numeric">{percent(group.ctr)}</td>
            <td className="numeric">{rate(group.cpc)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
