import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import type { DeliveriesPage, Delivery } from "../api/types";
import { DeliveryDetail } from "../components/DeliveryDetail";
import { HealthGrid } from "../components/HealthGrid";
import { StatusIcon } from "../components/icons";
import { count } from "../lib/format";
import { platformLabel } from "../lib/labels";
import { buildGrid, slotKey } from "../lib/slots";

/**
 * How many rows a slot would have held, had its file arrived.
 *
 * Taken as the most common row count among that platform's deliveries that did arrive. A mode
 * rather than an average, because the last week of the month is legitimately short and would
 * drag a mean down to a number no week ever had.
 */
function expectedRows(deliveries: Delivery[], platform: string): number | null {
  const tally = new Map<number, number>();
  for (const delivery of deliveries) {
    if (delivery.platform !== platform || delivery.is_missing) continue;
    tally.set(delivery.rows_total, (tally.get(delivery.rows_total) ?? 0) + 1);
  }

  let best: number | null = null;
  let bestSeen = 0;
  for (const [rows, seen] of tally) {
    if (seen > bestSeen) {
      best = rows;
      bestSeen = seen;
    }
  }
  return best;
}

export function HealthPage() {
  const [params, setParams] = useSearchParams();
  const deliveries = useApi<DeliveriesPage>(() => api.deliveries(), "deliveries");

  // The selection is (platform, week), not a delivery id: a slot can hold two files, and a
  // delivery id is a file name, so putting one in the URL would put ".json" in the URL.
  const platform = params.get("platform");
  const weekStart = params.get("week");
  const selected = platform && weekStart ? { platform, weekStart } : null;

  const all = deliveries.data?.deliveries ?? [];
  const grid = buildGrid(all);
  const slot = selected ? grid.slots.get(slotKey(selected.platform, selected.weekStart)) : undefined;

  // A missing delivery has no file and therefore no checks to show, so the drill-down lists
  // only the ids that actually have a record to fetch.
  const deliveryIds = (slot?.deliveries ?? [])
    .filter((delivery) => !delivery.is_missing)
    .map((delivery) => delivery.delivery_id);

  const counts = { pass: 0, warn: 0, fail: 0 };
  let missing = 0;
  for (const delivery of all) {
    counts[delivery.health] += 1;
    if (delivery.is_missing) missing += 1;
  }
  const received = all.length - missing;

  const slotIsMissing = slot !== undefined && slot.deliveries.every((d) => d.is_missing);
  const expected = slot && slotIsMissing ? expectedRows(all, slot.platform) : null;

  return (
    <div className="page">
      {deliveries.error && (
        <p className="error">
          {deliveries.error.message} ({deliveries.error.code})
        </p>
      )}
      {deliveries.loading && !deliveries.data && <p className="muted">loading&hellip;</p>}

      {deliveries.data && (
        <>
          <div className="health-head">
            <h1>Data health</h1>
            <p>
              <strong>{count(all.length)} deliveries</strong>: {count(received)} files received,{" "}
              {count(missing)} missing &middot; {counts.pass} pass &middot; {counts.warn} warn{" "}
              &middot; {counts.fail} fail
            </p>
          </div>

          <HealthGrid
            deliveries={all}
            selected={selected}
            onSelect={(nextPlatform, nextWeek) =>
              setParams(new URLSearchParams({ platform: nextPlatform, week: nextWeek }))
            }
          />

          {slot && slotIsMissing ? (
            <section className="detail" aria-label="Selected delivery">
              <div className="detail-head">
                <div className="detail-title">
                  {/* No file arrived, so there is no file name to set in mono. */}
                  <h2>
                    {platformLabel(slot.platform)}, week of {slot.weekStart}
                  </h2>
                  <span className="badge missing">
                    <StatusIcon status="missing" size={14} />
                    <span className="cap">missing</span>
                  </span>
                </div>
              </div>

              <div className="wrong">
                <h3>What&rsquo;s wrong</h3>
                <ul className="problems">
                  <li className="missing">
                    <StatusIcon status="missing" size={18} />
                    <span>
                      No file arrived for {platformLabel(slot.platform)}, week of {slot.weekStart}.
                      {expected !== null && ` ${count(expected)} rows expected.`}
                    </span>
                  </li>
                </ul>
              </div>

              <p className="muted">
                There is nothing to check, because nothing arrived. The slot is still shown
                because a delivery that never turns up is itself the defect.
              </p>
            </section>
          ) : (
            <DeliveryDetail deliveryIds={deliveryIds} />
          )}
        </>
      )}
    </div>
  );
}
