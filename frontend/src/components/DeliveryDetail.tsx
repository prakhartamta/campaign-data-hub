import { api } from "../api/client";
import { useApi } from "../api/useApi";
import type { Check, DeliveryDetail as Detail, RejectedRow } from "../api/types";
import { exclusionType, originalValues } from "../lib/excluded";
import { count } from "../lib/format";
import { checkLabel, levelLabel, levelRank, platformLabel } from "../lib/labels";
import { DisclosureChevrons, StatusIcon } from "./icons";

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
 * different shape: a coverage gap is (campaign, date) while an unreadable field is
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
    <table className="data-table examples">
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

  return (
    <div className="wrong">
      <h3>What&rsquo;s wrong</h3>
      {failed.length === 0 ? (
        <p className="muted">No problems found.</p>
      ) : (
        <ul className="problems">
          {failed.map((check) => (
            <li key={check.check_name} className={check.status}>
              <StatusIcon status={check.status} size={18} />
              <span>
                {/* The message is the API's own sentence, counts included. Rewriting it here is
                    how a UI ends up describing something other than what the check decided. */}
                <b className="cap">{check.status}</b> &middot; {check.message}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RowCounts({ delivery }: { delivery: Detail }) {
  const cells: [string, number][] = [
    ["accepted", delivery.rows_accepted],
    ["rejected", delivery.rows_rejected],
    ["suppressed", delivery.rows_suppressed],
    ["total", delivery.rows_total],
  ];
  return (
    <dl className="counts">
      {cells.map(([label, value]) => (
        <div key={label}>
          <dt className="cap">{label}</dt>
          <dd>{count(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function ExcludedRows({ rows }: { rows: RejectedRow[] }) {
  if (rows.length === 0) return null;

  return (
    <div className="detail-block">
      <h3>
        Excluded rows <span className="count">({rows.length})</span>
      </h3>
      <div className="table-card">
        <table className="data-table">
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
                    <span className={`tag ${type}`}>
                      <span className="cap">{type}</span>
                    </span>
                  </td>
                  <td className="reason-cell">{row.reasons.join("; ")}</td>
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
      </div>
    </div>
  );
}

function AllChecks({ checks }: { checks: Check[] }) {
  const ordered = [...checks].sort(byUrgency);
  // <details> is the disclosure: it is collapsed by default and reopens closed on a new
  // selection, because OneDelivery is keyed by delivery id and remounts.
  return (
    <details className="all-checks">
      <summary>
        <DisclosureChevrons />
        All checks ({checks.length})
      </summary>
      <div className="table-card">
        <table className="data-table checks-table">
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
                <td>
                  <span className="cap">{checkLabel(check.check_name)}</span>
                </td>
                <td>
                  <span className="cap">{levelLabel(check.level)}</span>
                </td>
                <td>
                  <span className="cap">{check.severity}</span>
                </td>
                <td>
                  <span className="check-result">
                    <StatusIcon status={check.status} size={14} />
                    <span className="cap">{check.status}</span>
                  </span>
                </td>
                <td className="numeric">{checkedRatio(check)}</td>
                <td className="message">
                  {check.message}
                  <Examples check={check} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
    <section className="detail" aria-label="Selected delivery">
      <div className="detail-head">
        <div className="detail-title">
          {/* The delivery id is the file name, so it is set in mono. */}
          <h2 className="mono">{data.delivery_id}</h2>
          <span className={`badge ${data.health}`}>
            <StatusIcon status={data.health} size={14} />
            <span className="cap">{data.health}</span>
          </span>
        </div>
        <p className="reason">
          {platformLabel(data.platform)}, week of {data.week_start} &middot; {data.health_reason}
        </p>
      </div>

      {/* What's wrong gets the width; the counts sit beside it rather than above the fold. */}
      <div className="detail-cols">
        <WhatIsWrong checks={data.checks} />
        <RowCounts delivery={data} />
      </div>

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
