import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import type { Delivery, DeliveriesPage, MetricsSummary } from "../api/types";
import { CampaignTable } from "../components/CampaignTable";
import type { SortDirection, SortKey } from "../components/CampaignTable";
import { Filters, platformsFrom } from "../components/Filters";
import type { FilterValues } from "../components/Filters";
import { RunIngestionButton } from "../components/RunIngestionButton";
import { TotalsBar } from "../components/TotalsBar";

const SORT_KEYS: SortKey[] = [
  "campaign",
  "platform",
  "rows",
  "spend_usd",
  "impressions",
  "clicks",
  "ctr",
  "cpc",
];

/**
 * Whether a delivery's week overlaps the date range the filters ask for.
 *
 * ISO dates compare correctly as strings. An unset bound is open, and a delivery with no week
 * cannot be placed in time, so it only counts when no range is set.
 */
function overlapsRange(delivery: Delivery, dateFrom: string, dateTo: string): boolean {
  if (dateFrom !== "" && (delivery.week_end === null || delivery.week_end < dateFrom)) {
    return false;
  }
  if (dateTo !== "" && (delivery.week_start === null || delivery.week_start > dateTo)) {
    return false;
  }
  return true;
}

/**
 * A filter that matches nothing is usually not an empty database but a delivery that was
 * quarantined or never arrived. Naming it turns a blank table into an explanation.
 *
 * Only deliveries inside the filtered platform and dates are named: a June file cannot explain
 * an empty October. The reason text is the API's own health_reason, never re-derived here.
 */
function EmptyState({ filters, deliveries }: { filters: FilterValues; deliveries: Delivery[] }) {
  const blamed = deliveries.filter(
    (delivery) =>
      delivery.health !== "pass" &&
      delivery.rows_accepted === 0 &&
      // A byte-identical resend never explains a gap: its original's rows are already counted.
      delivery.duplicate_of === null &&
      (filters.platform === "" || delivery.platform === filters.platform) &&
      overlapsRange(delivery, filters.dateFrom, filters.dateTo),
  );

  return (
    <div className="empty">
      <p className="empty-title">No campaign-days match these filters.</p>
      {blamed.length > 0 && (
        <>
          <p>These deliveries contributed no rows:</p>
          <ul>
            {blamed.map((delivery) => (
              <li key={delivery.delivery_id}>
                <strong>{delivery.delivery_id}</strong> &mdash; {delivery.health_reason}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export function CampaignsPage() {
  const [params, setParams] = useSearchParams();

  const values: FilterValues = {
    platform: params.get("platform") ?? "",
    dateFrom: params.get("from") ?? "",
    dateTo: params.get("to") ?? "",
  };

  // Read back through a whitelist: these come from the URL, which anyone can edit.
  const rawSort = params.get("sort") ?? "";
  const sort: SortKey = SORT_KEYS.includes(rawSort as SortKey) ? (rawSort as SortKey) : "spend_usd";
  const direction: SortDirection = params.get("dir") === "asc" ? "asc" : "desc";

  const query = new URLSearchParams({ group_by: "campaign" });
  if (values.platform) query.set("platform", values.platform);
  if (values.dateFrom) query.set("date_from", values.dateFrom);
  if (values.dateTo) query.set("date_to", values.dateTo);
  const key = query.toString();

  const summary = useApi<MetricsSummary>(() => api.summary(key), key);
  const deliveries = useApi<DeliveriesPage>(() => api.deliveries(), "deliveries");

  // True while an ingestion run is in progress. The button owns the run; the page only needs to
  // know one is happening, to show it on the numbers it is about to replace.
  const [ingesting, setIngesting] = useState(false);

  function update(next: Partial<FilterValues>) {
    const merged = { ...values, ...next };
    const nextParams = new URLSearchParams();
    if (merged.platform) nextParams.set("platform", merged.platform);
    if (merged.dateFrom) nextParams.set("from", merged.dateFrom);
    if (merged.dateTo) nextParams.set("to", merged.dateTo);
    nextParams.set("sort", sort);
    nextParams.set("dir", direction);
    setParams(nextParams);
  }

  function sortBy(nextKey: SortKey) {
    const nextParams = new URLSearchParams(params);
    nextParams.set("sort", nextKey);
    // Clicking the active column flips it; a new column starts descending, which is what you
    // want first for every money and volume column on this page.
    nextParams.set("dir", sort === nextKey && direction === "desc" ? "asc" : "desc");
    setParams(nextParams);
  }

  function clear() {
    setParams(new URLSearchParams({ sort, dir: direction }));
  }

  const groups = summary.data?.groups ?? [];
  const firstLoad = summary.loading && summary.data === null;
  // Skeletons stand in for the numbers on a first load, and during a run, when everything on
  // screen is about to be replaced. A filter change keeps the current answer up until the next
  // one lands: that takes tens of milliseconds, and a skeleton that brief would only flicker.
  const showSkeleton = firstLoad || ingesting;

  return (
    <div className="page">
      <div className="title-row">
        <h1>Campaigns</h1>
        <RunIngestionButton
          onDone={() => {
            summary.reload();
            deliveries.reload();
          }}
          onRunningChange={setIngesting}
        />
      </div>

      <Filters
        values={values}
        platforms={platformsFrom(deliveries.data?.deliveries ?? [])}
        onChange={update}
        onClear={clear}
      />

      {summary.error && (
        <p className="error">
          {summary.error.code}: {summary.error.message}
        </p>
      )}

      <TotalsBar totals={summary.data?.totals ?? null} loading={showSkeleton} />

      {/* The table keeps its frame and header through every state, so the page has one shape
          whether it is loading, empty or full. Only a failed first load has no table at all. */}
      {(showSkeleton || summary.data) && (
        <CampaignTable
          groups={groups}
          sort={sort}
          direction={direction}
          onSort={sortBy}
          loading={showSkeleton}
          empty={
            <EmptyState filters={values} deliveries={deliveries.data?.deliveries ?? []} />
          }
        />
      )}
    </div>
  );
}
