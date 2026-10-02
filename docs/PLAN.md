# Build plan

Working notes. Data evidence is in [findings.md](findings.md). `ASSIGNMENT.md` is the source of
truth for requirements.

## Precision contract

Settled before the row model, because getting it wrong means a schema change rather than a fix.

1. Sum at full precision, round **once**, at the API boundary, half-up.
2. Spend is integer **micro-USD**. No `NUMERIC(12,2)`, no `round(x, 2)` per row, no
   `micros // 10000`.
3. Rates as `Decimal(str(rate))`, read from `document["rates"]`.
4. Epoch dates as `fromtimestamp(ms / 1000, tz=timezone.utc).date()`.
5. Parse with `except (ValueError, ArithmeticError, TypeError)`.
6. All CSV through the `csv` module, never a manual split.

## Pipeline

One function, called by both the CLI and the API.

1. **Discover** — glob `data/deliveries/*`, keep `.csv`/`.json`, skip dotfiles. Build the
   platform x week grid from config so an empty slot is still a record.
2. **Per file, isolated** — parse, adapt, row checks, file checks. Every check wrapped so an
   exception records `status="error"` and the run continues.
3. **Resolve slots** — missing, unrecognized, duplicate, conflict. Decides which deliveries
   contribute rows.
4. **Aggregate checks** — each delivery against its own platform's other deliveries. Quarantine
   decisions land here.
5. **Resolve campaign identity** across all accepted rows.
6. **Collapse to the canonical key** in memory, then assert the count matches, so a collision is a
   loud failure rather than an `IntegrityError` that rolls back the run.
7. **Classify health** per delivery, then per slot.
8. **Persist** in one transaction, as a full recompute.

## Storage (SQLite)

| Table | Key | Notes |
|---|---|---|
| `deliveries` | file name | an empty slot uses the *expected* name; `rows_total = accepted + rejected + suppressed` |
| `check_results` | (delivery_id, check_name) | counts, message, up to 5 sorted samples |
| `metrics` | (platform, campaign, date) | `spend_usd_micros` + lineage incl. `raw_spend_unit` |
| `rejected_rows` | (delivery_id, source_row) | reasons as a list |
| `ingestion_runs` | run id | the only table that grows |

`rows_rejected` counts row-level validity failures only; `rows_suppressed` counts rows removed by
dedupe, duplicate file or quarantine. Keeping them apart is what stops a file that is clean after
dedupe from being reported as failing.

## Checks — 15

| # | Name | Level | Sev | Action | Fires |
|---|---|---|---|---|---|
| 1 | `required_fields_present` | row | fail | reject | R2, R4 |
| 2 | `values_parseable` | row | fail | reject | R1 |
| 3 | `metrics_non_negative` | row | fail | reject | R3 |
| 4 | `clicks_not_above_impressions` | row | fail | reject | — |
| 5 | `date_within_delivery_week` | row | fail | reject | — (timezone safety net) |
| 6 | `currency_in_rates_file` | row | fail | reject | — |
| 7 | `campaign_name_normalized` | row | warn | flag | N1, N3 |
| 8 | `date_format_normalized` | row | warn | flag | N2 |
| 9 | `file_structure_valid` | file | fail | quarantine | — |
| 10 | `duplicate_rows_within_file` | file | warn | drop | N4 |
| 11 | `spend_scale_vs_platform_baseline` | file | fail | quarantine | **F1** |
| 12 | `campaign_day_coverage` | file | warn | flag | R1, R2, R4 knock-on |
| 13 | `delivery_present` | delivery | fail | flag | **D1** |
| 14 | `file_name_matches_convention` | delivery | warn | flag | D2 |
| 15 | `duplicate_delivery_content` | delivery | warn | drop | **D2** |

11 fire, 4 are correctness guards. `drop` is a fourth action beyond reject/quarantine/flag: without
it, "keep one duplicate and flag it" has no mechanism, all 43 Google rows hit the INSERT, and the
metrics PK rolls back the whole transaction.

Row checks are plausibility bounds only, never statistical. Measured: per-campaign CPC spans 8.5x,
so a row-level ratio check would need to be looser than 3x to be clean, at which point it catches
only the 100x cents defect. Statistics live at aggregate level.

**Deferred** (in NOTES.md): `duplicate_keys_within_file`, `row_volume_vs_platform_baseline`,
`single_file_per_slot`, `platform_recognized` as a separate check, cross-delivery key uniqueness as
a separate check. None fires on this data.

## Health — first match wins

| # | Condition | Health |
|---|---|---|
| 1 | slot has no file | FAIL |
| 2 | quarantined | FAIL |
| 3 | a different file already holds this slot | FAIL |
| 4 | byte-identical duplicate (superseded) | WARN |
| 5 | a fail-severity check failed **or errored** | FAIL |
| 6 | `rows_rejected / rows_total > 10%` | FAIL |
| 7 | a warn-severity check failed, or any row rejected, suppressed or normalized | WARN |
| 8 | otherwise | PASS |

Ordered rather than an OR, because the original rules contradicted themselves on two deliveries:
Google 06-01 at 8/43 = 18.6% would FAIL despite being clean after dedupe, and the resend at 0-of-35
would FAIL despite the policy promising WARN. Row 5 includes `errored` because otherwise a crashed
check leaves the delivery PASS — the exact failure the brief opens with.

Expected: **8 PASS, 5 WARN, 3 FAIL** across 16 records.

## API

| Method | Path |
|---|---|
| POST | `/api/v1/ingestions` — 201 + summary, 409 if running |
| GET | `/api/v1/ingestions/{run_id}` |
| GET | `/api/v1/metrics` — daily rows + lineage, filters, limit/offset + total |
| GET | `/api/v1/metrics/summary?group_by=campaign\|platform` — `{filters, totals, groups[]}` |
| GET | `/api/v1/deliveries?platform=&health=` |
| GET | `/api/v1/deliveries/{delivery_id}` — checks + rejected samples |
| GET | `/healthz` — liveness, outside `/api/v1` |

CTR and CPC are ratios of sums, never averages of ratios; `null` on a zero denominator. An empty
result returns zeroed totals with nulls, never a 404. Explicit `ORDER BY` on every list endpoint,
or the live run-twice diff fails on row ordering alone. One error envelope
`{"error": {code, message, details}}` via handlers for `RequestValidationError`,
`StarletteHTTPException` and a catch-all. The ingestion handler is `def`, not `async def`, so the
synchronous pipeline runs in the threadpool and the 409 branch stays demonstrable.

## Frontend

`CampaignsPage` (Filters, TotalsBar, sortable CampaignTable, RunIngestionButton) and `HealthPage`
(HealthGrid, DeliveryDetail). Filters and sort key in URL params. Totals always from the API.
Sorting is client-side over ~13 grouped rows. Grid cells are **slots**, not deliveries, so a slot
holding two files has a defined colour; routed by `(platform, weekStart)` to avoid a `.json` in the
URL. The empty state names the quarantined or missing delivery, since those filters return zero rows
and would otherwise look like a broken page.

## Phases

| Phase | Done when |
|---|---|
| 1 | Two runs print identical per-file parsed totals (403 rows, 9 parse failures); adapter tests pass |
| 2 | Every defect maps to a named check; totals match findings.md; health is 8/5/3; idempotency and error-isolation tests pass |
| 3 | Endpoints work at `/docs`; API tests pass |
| 4 | Both pages work end to end incl. sorting and empty states |
| 5 | `docker compose up --build` serves a working app with data |
| 6 | README; diagram checked against the code; fresh clone followed exactly |

The reference totals are a Phase 2 target, not Phase 1: they depend on dedupe, rejection and
quarantine, which are check decisions. `metrics` is not populated until Phase 2 for the same reason
— its key is only safe after step 6.

Never adjust a check to hit a target count. If a count disagrees with this plan, the plan is what
gets corrected.

## Tests — 10, synthetic fixtures only

1. Ingest twice, byte-identical output. 2. Adapters: units, FX, epoch, date formats.
3. `TZ=America/New_York` leaves dates unchanged. 4. Precision: round once, not per row.
5. A broken file does not abort the run. 6. Missing slot and duplicate file both detected.
7. Non-adjacent duplicates ingest once without an `IntegrityError`. 8. CTR from sums, CPC null at
zero clicks, empty filter returns zeroed totals. 9. 404, 400 and a validation 422 all return the
envelope. 10. Mixed case and whitespace collapse to one campaign.
