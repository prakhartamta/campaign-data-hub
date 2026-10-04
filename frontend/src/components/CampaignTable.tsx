import type { ReactNode } from "react";
import type { SummaryGroup } from "../api/types";
import { count, money, percent, rate, sortable } from "../lib/format";
import { platformLabel } from "../lib/labels";

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
  /** While true the rows give way to skeleton bars; the header, and sorting, stay. */
  loading?: boolean;
  /** Shown in place of the rows when the filters match nothing, inside the table's own frame. */
  empty?: ReactNode;
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
      // By the label, so the column sorts the way it reads on screen.
      order = platformLabel(left.platform).localeCompare(platformLabel(right.platform));
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

function Head({ sort, direction, onSort }: Pick<Props, "sort" | "direction" | "onSort">) {
  return (
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
            <button type="button" className="sort-btn" onClick={() => onSort(column.key)}>
              <span className="sort-label cap">{column.label}</span>
              {/* A fixed-width slot, so the label does not shift as the arrow moves column. */}
              <span className="sort-arrow" aria-hidden="true">
                {sort === column.key ? (direction === "asc" ? "↑" : "↓") : ""}
              </span>
            </button>
          </th>
        ))}
      </tr>
    </thead>
  );
}

/** Bar widths per column, so the skeleton has the shape of the table it stands in for. */
const BAR_WIDTHS = [88, 0, 24, 72, 72, 56, 40, 56];
// Campaign names vary in length, so their bars do too: one entry per skeleton row.
const CAMPAIGN_WIDTHS = [160, 120, 180, 140, 110, 170, 130, 150];

function SkeletonRows() {
  return (
    <>
      {CAMPAIGN_WIDTHS.map((campaignWidth, row) => (
        <tr key={row} className="skeleton-row">
          {COLUMNS.map((column, index) => (
            <td key={column.key} className={column.numeric ? "numeric" : undefined}>
              <span
                className="skeleton"
                style={{ width: index === 1 ? campaignWidth : BAR_WIDTHS[index] }}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function CampaignTable({
  groups,
  sort,
  direction,
  onSort,
  loading = false,
  empty,
}: Props) {
  const rows = sortGroups(groups, sort, direction);

  return (
    <div className="table-card" aria-busy={loading || undefined}>
      <table className="data-table campaigns-table">
        <Head sort={sort} direction={direction} onSort={onSort} />
        <tbody>
          {loading && <SkeletonRows />}
          {/* The header stays when there is nothing to show: the columns are part of the answer. */}
          {!loading && rows.length === 0 && empty !== undefined && (
            <tr>
              <td className="empty-cell" colSpan={COLUMNS.length}>
                {empty}
              </td>
            </tr>
          )}
          {!loading && rows.map((group) => (
            <tr key={`${group.platform}|${group.key}`}>
              <td>{platformLabel(group.platform)}</td>
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
    </div>
  );
}
