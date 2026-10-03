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
 * A filter that matches nothing is usually not an empty database but a delivery that was
 * quarantined or never arrived. Naming it turns a blank table into an explanation.
 *
 * The reason text is the API's own health_reason, never re-derived here.
 */
function EmptyState({ platform, deliveries }: { platform: string; deliveries: Delivery[] }) {
  const blamed = deliveries.filter(
    (delivery) =>
      delivery.health !== "pass" &&
      delivery.rows_accepted === 0 &&
      (platform === "" || delivery.platform === platform),
  );

  return (
    <div className="empty">
      <p>No campaign-days match these filters.</p>
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
  // A refetch, not a first load: the previous answer is still on screen, so it is dimmed in
  // place rather than removed. Taking the table away would make a 60ms recompute look like a
  // page that lost its data.
  const refreshing = summary.loading && summary.data !== null;

  return (
    <div className="page">
      <div className="page-head">
        <Filters
          values={values}
          platforms={platformsFrom(deliveries.data?.deliveries ?? [])}
          onChange={update}
          onClear={clear}
        />
        <RunIngestionButton
          onDone={() => {
            summary.reload();
            deliveries.reload();
          }}
        />
      </div>

      {summary.error && (
        <p className="error">
          {summary.error.code}: {summary.error.message}
        </p>
      )}

      {summary.loading && !summary.data && <p className="muted">loading&hellip;</p>}

      <div className={refreshing ? "refreshable is-refreshing" : "refreshable"}>
        {refreshing && (
          <span className="refresh-label" role="status">
            Refreshing…
          </span>
        )}

        <div className="refreshable-body">
          <TotalsBar totals={summary.data?.totals ?? null} />

          {summary.data && groups.length === 0 && (
            <EmptyState
              platform={values.platform}
              deliveries={deliveries.data?.deliveries ?? []}
            />
          )}

          {groups.length > 0 && (
            <CampaignTable groups={groups} sort={sort} direction={direction} onSort={sortBy} />
          )}
        </div>
      </div>
    </div>
  );
}
