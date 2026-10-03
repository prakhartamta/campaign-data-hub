import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import type { DeliveriesPage } from "../api/types";
import { DeliveryDetail } from "../components/DeliveryDetail";
import { HealthGrid } from "../components/HealthGrid";
import { buildGrid, slotKey } from "../lib/slots";

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
  for (const delivery of all) counts[delivery.health] += 1;

  return (
    <div className="page">
      {deliveries.error && (
        <p className="error">
          {deliveries.error.code}: {deliveries.error.message}
        </p>
      )}
      {deliveries.loading && !deliveries.data && <p className="muted">loading&hellip;</p>}

      {deliveries.data && (
        <>
          <p className="muted">
            {counts.pass} pass &middot; {counts.warn} warn &middot; {counts.fail} fail across{" "}
            {deliveries.data.total} expected deliveries
          </p>

          <HealthGrid
            deliveries={all}
            selected={selected}
            onSelect={(nextPlatform, nextWeek) =>
              setParams(new URLSearchParams({ platform: nextPlatform, week: nextWeek }))
            }
          />

          {slot && slot.deliveries.every((delivery) => delivery.is_missing) ? (
            <section className="detail">
              <h2>
                {slot.platform} {slot.weekStart}{" "}
                <span className="badge fail">missing</span>
              </h2>
              <p className="reason">{slot.deliveries[0]?.health_reason}</p>
              <p className="muted">
                No file arrived for this slot, so there is nothing to check. The slot is still
                shown because a delivery that never arrives is the defect.
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
