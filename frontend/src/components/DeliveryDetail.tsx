import { api } from "../api/client";
import { useApi } from "../api/useApi";
import type { Check, DeliveryDetail as Detail, RejectedRow } from "../api/types";
import { exclusionType, originalValues } from "../lib/excluded";
import { count } from "../lib/format";
import { checkLabel, levelLabel, levelRank, platformLabel } from "../lib/labels";

const EM_DASH = "—";

/** Not-passed first, then narrow to broad, so the reason a delivery is not green is at the top. */
function byUrgency(left: Check, right: Check): number {
  const leftFailed = left.status === "pass" ? 1 : 0;
  const rightFailed = right.status === "pass" ? 1 : 0;
  if (leftFailed !== rightFailed) return leftFailed - rightFailed;
  const byLevel = levelRank(left.level) - levelRank(right.level);
  return byLevel !== 0 ? byLevel : left.check_name.localeCompare(right.check_name);
}

/** A check that inspects the delivery rather than its rows has no ratio to report. */
function checkedRatio(check: Check): string {
  if (check.rows_checked === 0) return EM_DASH;
  return `${count(check.rows_failed)} / ${count(check.rows_checked)}`;
}

/**
 * The examples a check attached, as a table.
 *
 * Columns are the union of the keys present, in first-seen order, because every check attaches a
 * different shape: a coverage gap is (campaign, missing_date) while an unreadable field is
 * (source_row, field, raw_value, reason).
 */
function Examples({ check }: { check: Check }) {
  if (check.samples.length === 0) return null;

  const columns: string[] = [];
  for (const sample of check.samples) {
    for (const key of Object.keys(sample)) {
      if (!columns.includes(key)) columns.push(key);
    }
  }

  return (
    <table className="grid-table examples">
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column}>{column.replace(/_/g, " ")}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {check.samples.map((sample, index) => (
          <tr key={index}>
            {columns.map((column) => {
              const value = sample[column];
              return (
                <td key={column}>
                  {value === undefined || value === null ? EM_DASH : String(value)}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function WhatIsWrong({ checks }: { checks: Check[] }) {
  const failed = checks.filter((check) => check.status !== "pass").sort(byUrgency);

  if (failed.length === 0) {
    return (
      <>
        <h3>What&rsquo;s wrong</h3>
        <p className="muted">No problems found.</p>
      </>
    );
  }

  return (
    <>
      <h3>What&rsquo;s wrong</h3>
      <ul className="problems">
        {failed.map((check) => (
          <li key={check.check_name} className={check.status}>
            {/* The message is the API's own sentence, counts included. Rewriting it here is how
                a UI ends up describing something other than what the check decided. */}
            {check.message}
          </li>
        ))}
      </ul>
    </>
  );
}

function RowTiles({ delivery }: { delivery: Detail }) {
  const tiles: [string, number][] = [
    ["accepted", delivery.rows_accepted],
    ["rejected", delivery.rows_rejected],
    ["suppressed", delivery.rows_suppressed],
    ["total", delivery.rows_total],
  ];
  return (
    <div className="totals small">
      {tiles.map(([label, value]) => (
        <div className="tile" key={label}>
          <span className="tile-label">{label}</span>
          <span className="tile-value">{count(value)}</span>
        </div>
      ))}
    </div>
  );
}

function ExcludedRows({ rows }: { rows: RejectedRow[] }) {
  if (rows.length === 0) return null;

  return (
    <>
      <h3>Excluded rows ({rows.length})</h3>
      <table className="grid-table">
        <thead>
          <tr>
            <th className="numeric">source row</th>
            <th>type</th>
            <th>reason</th>
            <th>campaign</th>
            <th>date</th>
            <th className="numeric">spend</th>
            <th className="numeric">impressions</th>
            <th className="numeric">clicks</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const values = originalValues(row);
            const type = exclusionType(row);
            return (
              <tr key={row.source_row}>
                <td className="numeric">{row.source_row}</td>
                <td>
                  <span className={`tag ${type}`}>{type}</span>
                </td>
                <td>{row.reasons.join("; ")}</td>
                <td>{values.campaign}</td>
                <td>{values.date}</td>
                <td className="numeric">{values.spend}</td>
                <td className="numeric">{values.impressions}</td>
                <td className="numeric">{values.clicks}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

function AllChecks({ checks }: { checks: Check[] }) {
  const ordered = [...checks].sort(byUrgency);
  return (
    <details className="all-checks">
      <summary>All checks ({checks.length})</summary>
      <table className="grid-table">
        <thead>
          <tr>
            <th>check</th>
            <th>level</th>
            <th>if it fails</th>
            <th>result</th>
            <th className="numeric">failed / checked</th>
            <th>message</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((check) => (
            <tr key={check.check_name} className={`check ${check.status}`}>
              <td>{checkLabel(check.check_name)}</td>
              <td>{levelLabel(check.level)}</td>
              <td>{check.severity}</td>
              <td>{check.status}</td>
              <td className="numeric">{checkedRatio(check)}</td>
              <td>
                {check.message}
                <Examples check={check} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function OneDelivery({ id }: { id: string }) {
  const { data, error, loading } = useApi<Detail>(() => api.delivery(id), id);

  if (loading && !data) return <p className="muted">loading {id}&hellip;</p>;
  if (error) {
    return (
      <p className="error">
        {id}: {error.message} ({error.code})
      </p>
    );
  }
  if (!data) return null;

  return (
    <section className="detail">
      <h2>
        {data.delivery_id} <span className={`badge ${data.health}`}>{data.health}</span>
      </h2>
      <p className="reason">
        {platformLabel(data.platform)}, week of {data.week_start} &middot; {data.health_reason}
      </p>

      <WhatIsWrong checks={data.checks} />
      <RowTiles delivery={data} />
      <ExcludedRows rows={data.rejected_rows} />
      <AllChecks checks={data.checks} />
    </section>
  );
}

// A slot can hold two files, so the drill-down takes ids rather than one id and stacks them.
export function DeliveryDetail({ deliveryIds }: { deliveryIds: string[] }) {
  if (deliveryIds.length === 0) {
    return <p className="muted">Select a cell to see its checks.</p>;
  }
  return (
    <>
      {deliveryIds.map((id) => (
        <OneDelivery key={id} id={id} />
      ))}
    </>
  );
}
