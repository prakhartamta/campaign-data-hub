import { Fragment } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import type { Check, DeliveryDetail as Detail, RejectedRow } from "../api/types";
import { count } from "../lib/format";

// Checks that passed are collapsed by default: a reviewer opening a delivery is looking for what
// went wrong, and twelve green rows push the one red row off the screen.
function CheckRow({ check }: { check: Check }) {
  return (
    <tr className={`check ${check.status}`}>
      <td>{check.check_name}</td>
      <td>{check.level}</td>
      <td>{check.severity}</td>
      <td>{check.status}</td>
      <td className="numeric">
        {check.rows_failed} / {check.rows_checked}
      </td>
      <td>{check.message}</td>
    </tr>
  );
}

function Samples({ check }: { check: Check }) {
  if (check.samples.length === 0) return null;
  return (
    <tr className="samples">
      <td colSpan={6}>
        <strong>{check.check_name}</strong> examples
        <pre>{JSON.stringify(check.samples, null, 2)}</pre>
      </td>
    </tr>
  );
}

function RejectedRows({ rows }: { rows: RejectedRow[] }) {
  if (rows.length === 0) return null;
  return (
    <>
      <h3>excluded rows ({rows.length})</h3>
      <table className="grid-table">
        <thead>
          <tr>
            <th>source row</th>
            <th>blamed</th>
            <th>reasons</th>
            <th>original values</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.source_row}>
              <td className="numeric">{row.source_row}</td>
              {/* blamed false means the row was fine but removed as a duplicate or by a
                  quarantine, so it is not counted against the delivery. */}
              <td>{row.blamed ? "yes" : "no"}</td>
              <td>{row.reasons.join("; ")}</td>
              <td>
                <code>{JSON.stringify(row.raw)}</code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function OneDelivery({ id }: { id: string }) {
  const { data, error, loading } = useApi<Detail>(() => api.delivery(id), id);

  if (loading && !data) return <p className="muted">loading {id}…</p>;
  if (error) {
    return (
      <p className="error">
        {id}: {error.code} {error.message}
      </p>
    );
  }
  if (!data) return null;

  const failing = data.checks.filter((check) => check.status !== "pass");
  const passing = data.checks.filter((check) => check.status === "pass");

  return (
    <section className="detail">
      <h2>
        {data.delivery_id} <span className={`badge ${data.health}`}>{data.health}</span>
      </h2>

      {/* The health reason comes from the API, which recorded the single condition that decided
          it. Re-deriving it here is how a UI ends up contradicting its own backend. */}
      <p className="reason">{data.health_reason}</p>

      <dl className="facts">
        <dt>week</dt>
        <dd>
          {data.week_start} to {data.week_end}
        </dd>
        <dt>rows</dt>
        <dd>
          {count(data.rows_accepted)} accepted, {count(data.rows_rejected)} rejected,{" "}
          {count(data.rows_suppressed)} suppressed of {count(data.rows_total)}
        </dd>
        {data.duplicate_of && (
          <>
            <dt>supersedes</dt>
            <dd>{data.duplicate_of}</dd>
          </>
        )}
        {data.has_name_suffix && (
          <>
            <dt>file name</dt>
            <dd>does not match the expected convention</dd>
          </>
        )}
        {data.structural_error && (
          <>
            <dt>structural error</dt>
            <dd>{data.structural_error}</dd>
          </>
        )}
        {data.content_hash && (
          <>
            <dt>content hash</dt>
            <dd>
              <code>{data.content_hash.slice(0, 16)}…</code>
            </dd>
          </>
        )}
      </dl>

      <h3>checks</h3>
      <table className="grid-table">
        <thead>
          <tr>
            <th>check</th>
            <th>level</th>
            <th>severity</th>
            <th>status</th>
            <th className="numeric">failed / checked</th>
            <th>message</th>
          </tr>
        </thead>
        <tbody>
          {failing.map((check) => (
            <Fragment key={check.check_name}>
              <CheckRow check={check} />
              <Samples check={check} />
            </Fragment>
          ))}
          {passing.map((check) => (
            <CheckRow key={check.check_name} check={check} />
          ))}
        </tbody>
      </table>

      <RejectedRows rows={data.rejected_rows} />
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
