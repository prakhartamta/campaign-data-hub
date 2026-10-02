# Campaign Data Hub — agreed build plan

Working document, agreed at the end of Phase 0. Where this file differs from the original brief-to-self, this
file wins. Data findings and their evidence live in [findings.md](findings.md). `ASSIGNMENT.md` remains the
source of truth for requirements.

---

## 1. Precision contract — settled before any row model is written

1. Convert and sum at **full precision**; quantize **once** at the API boundary with `ROUND_HALF_UP`.
2. Store integer **micro-USD**. Never `round(x, 2)` per row, never a `NUMERIC(12,2)` spend column, never
   `micros // 10000`, never `int()` or `floor`. Micro-USD is lossless for every row in this data: EUR amounts
   have 2 decimals and the rate has 2, so USD has at most 4.
3. Rates as `Decimal(str(rate))`, read from `j["rates"]`.
4. Epoch dates as `datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()`. Never `utcfromtimestamp`
   (deprecated in 3.12).
5. Parse rows with `except (ValueError, ArithmeticError, TypeError)`, because `Decimal('')` raises
   `InvalidOperation` (an `ArithmeticError`) while `int('')` raises `ValueError`.
6. All CSV parsing goes through the `csv` module. Never split a line by hand.

Rationale and the exact dollar consequences of getting any of these wrong: findings.md §7.

---

## 2. Pipeline — 8 steps, one function, called by both the CLI and the API

1. **Discover.** Glob `data/deliveries/*`, keep `.csv` and `.json`, **skip dotfiles**. Parse each name as
   `<platform>_<week-start>.<ext>`; anything trailing (`_resend`) marks a non-standard name. Build the expected
   slot grid from config so an empty slot still becomes a delivery record.
2. **Per file, isolated.** parse → adapter → canonical rows → row checks → file checks. Every check wrapped so
   an exception records `status="error"` and the run continues (NFR-2).
3. **Resolve slots.** Missing, unrecognized, byte-identical duplicate, more than one file per slot. Decides
   which deliveries contribute rows.
4. **Aggregate-level checks** on contributing deliveries, each against its own platform's other deliveries.
   Quarantine decisions land here.
5. **Resolve campaign identity** across all accepted rows: trim and case-fold, group case-insensitively,
   display the most common spelling, tie broken by `(count desc, spelling asc)` so the primary key is
   deterministic. Only accepted rows vote. Never `.title()`.
6. **Collapse to the canonical key.** Build a dict keyed `(platform, campaign, date)`; dedupe and
   conflict-resolve **in memory**, then `assert len(dict) == rows_accepted` so a future collision is a loud
   invariant failure rather than an `IntegrityError` that rolls back the whole run.
7. **Classify health** per delivery, then per slot.
8. **Persist** in ONE transaction, as a full recompute.

Step 6 exists because the original design had no mechanism for "keep one duplicate, flag it": the only check
actions were reject / quarantine / flag. Under flag-only, all 43 rows of `google_ads_2026-06-01.csv` reach the
INSERT, the `metrics` primary key raises `UNIQUE constraint failed`, and since all 16 deliveries persist in one
transaction **the entire run rolls back** — zero rows and no quality report explaining why. Hence the new
`drop_row` action and the in-memory collapse.

---

## 3. Storage — SQLite, WAL, money as integer micro-USD

- **`deliveries`** — `id` = file name (an empty slot gets a row whose id is the *expected* file name, with no
  file); platform, week_start, week_end, content_hash, duplicate_of, health, rows_total, rows_accepted,
  **rows_rejected**, **rows_suppressed**.
  Invariant: `rows_total = rows_accepted + rows_rejected + rows_suppressed`, where *rejected* means failed a
  row-level validity check and *suppressed* means removed by a file- or delivery-level action (dedupe,
  duplicate file, quarantine). Keeping these separate is what resolves the health contradiction in §5.
- **`check_results`** — PK `(delivery_id, check_name)`; level, severity, status, rows_checked, rows_failed,
  message, samples JSON (max 5, explicitly sorted). `fail_rate` is a computed property, not a column.
- **`metrics`** — PK `(platform, campaign, date)`; spend_usd_micros, impressions, clicks; lineage
  `delivery_id, source_row, raw_spend, raw_spend_unit, raw_currency, fx_rate`, plus nullable `raw_campaign`
  and `raw_date` populated only when they differ from the canonical value.
  `raw_spend_unit` is required because Google's raw spend is micros, Meta's is dollars and LinkedIn's is EUR
  units — one column without a unit would render `$117,410,000` beside a normalized `$117.41`. The nullable raw
  fields are what make a normalization demonstrable: that `(meta, Brand Awareness Q2, 2026-06-04)` came from
  the literal `brand awareness q2` at line 12.
- **`rejected_rows`** — PK `(delivery_id, source_row)`; reasons JSON (a **list** — all failing row checks are
  collected, not short-circuited), raw JSON.
- **`ingestion_runs`** — the only table that grows. Committed in its own transaction before the recompute and
  updated after, so a failed run is still visible.

---

## 4. Check catalog — 20 checks, 11 fire on this data, 9 are general guards

Mapped onto the five dimensions the brief names: completeness, validity, duplication, volume, cadence.

| # | Name | Level | Sev | On fail | Fires |
|---|---|---|---|---|---|
| 1 | `required_fields_present` | row | fail | reject_row | R2, R4 |
| 2 | `values_parseable` | row | fail | reject_row | R1 |
| 3 | `metrics_non_negative` | row | fail | reject_row | R3 |
| 4 | `clicks_not_above_impressions` | row | fail | reject_row | — |
| 5 | `date_within_delivery_week` | row | fail | reject_row | — (safety net for a wrong date format) |
| 6 | `currency_in_rates_file` | row | fail | reject_row | — (cannot cover Meta: no currency column) |
| 7 | `campaign_name_normalized` | row | warn | flag | N1, N3 |
| 8 | `date_format_normalized` | row | warn | flag | N2 |
| 9 | `file_structure_valid` | file | fail | quarantine_file | — |
| 10 | `duplicate_rows_within_file` | file | warn | drop_row | N4 |
| 11 | `duplicate_keys_within_file` | file | fail | reject_row (all copies) | — |
| 12 | `spend_scale_vs_platform_baseline` | file | fail | quarantine_file | **F1** |
| 13 | `row_volume_vs_platform_baseline` | file | warn | flag | — |
| 14 | `campaign_day_coverage` | file | warn | flag | R1, R2, R4 second-order |
| 15 | `delivery_present` | delivery | fail | flag | **D1** |
| 16 | `file_name_matches_convention` | delivery | warn | flag | D2 |
| 17 | `duplicate_delivery_content` | delivery | warn | drop_row | **D2** |
| 18 | `single_file_per_slot` | delivery | fail | flag | — |
| 19 | `platform_recognized` | delivery | fail | flag | — |
| 20 | `canonical_key_unique_across_deliveries` | delivery | fail | reject_row (all copies) | — (protects the `metrics` PK) |

Adding a check means adding one class and editing nothing else. Every check is wrapped so an exception records
`status="error"` and the run continues.

**#12** compares the file's median CPM against the median of that platform's other deliveries; quarantine
outside `[1/10, 10]`. CPM is per-impression, so no short-week normalization is needed. The defective file is
~103x and every clean file is within 1.2x of its platform baseline, so the threshold has roughly 10x of margin
on both sides. The check also reports the inferred factor (nearest power of ten) and the total the delivery
*would* contribute at that factor, which is what gives the README its exact alternative number.

**#13** uses accepted rows per **covered day** versus the platform's other deliveries; WARN outside
`[0.5, 2.0]`. Day-normalization is mandatory: a raw week-over-week comparison would false-FAIL all three
06-29 deliveries at −63% to −72% on clean data.

**#14** compares accepted `(campaign, date)` pairs against `campaigns_seen x days_covered` after rejections and
names the specific holes — *"App Install Push lost 2026-06-01"*, *"LinkedIn has no data for 2026-06-14"*.
More informative than a row count, and the signal a stakeholder notices first.

**#15** reports the empty slot and its expected row count (3 campaigns x 7 days = 21 for D1). No extrapolated
dollar estimate inside the check — a neighbouring-week extrapolation is not something the check can know. The
magnitude estimate belongs in the README findings section, sourced from findings.md §5.

Row-level checks are deliberately **plausibility bounds only**, never statistical. Measured justification in
findings.md §9: natural per-campaign day-to-day variance is wide enough (CPC spans 8.5x) that a row-level
median-ratio check would have to be looser than 3x to be clean, at which point it catches the 100x cents
defect and nothing else. Statistics live at file and delivery aggregate level.

---

## 5. Health — an ordered precedence list, first match wins

| # | Condition | Health |
|---|---|---|
| 1 | expected slot has no file | FAIL |
| 2 | delivery quarantined | FAIL |
| 3 | a different file already occupies this slot | FAIL |
| 4 | byte-identical duplicate of another delivery (superseded) | WARN |
| 5 | any fail-severity check **failed or errored** | FAIL |
| 6 | `rows_rejected / rows_total > 10%` (validity rejections only) | FAIL |
| 7 | any warn-severity check failed, or any row rejected, suppressed or normalized | WARN |
| 8 | otherwise | PASS |

A precedence list rather than an OR of conditions, because the original rules contradicted themselves on 2 of
15 deliveries: `google_ads_2026-06-01.csv` would be 8 dropped duplicates / 43 = 18.6% > 10% → FAIL although it
is perfectly clean after dedupe, and the resend would be 0 accepted of 35 = 100% → FAIL although the policy
promises WARN. Splitting `rows_rejected` from `rows_suppressed` fixes the arithmetic; the ordering fixes the
ambiguity.

Row 5 closes a second hole: `status="error"` was governed by no rule at all, so a crashed check left a delivery
**PASS** — reintroducing the exact "nobody notices when a delivery arrives broken" failure the brief opens
with, through the mechanism meant to prevent it. **An errored check inherits its declared severity.**

Thresholds live in `config.py` and this table is reproduced in the README.

### Expected outcome on this data: 8 PASS, 5 WARN, 3 FAIL across 16 records

| Platform | 06-01 | 06-08 | 06-15 | 06-22 | 06-29 | extra |
|---|---|---|---|---|---|---|
| google | WARN (8 dup rows) | PASS | PASS | PASS | PASS | `_resend` WARN (superseded) |
| linkedin | PASS | FAIL (5/21 = 23.8% rejected) | PASS | FAIL (missing) | PASS | — |
| meta | WARN (1 reject, 3 casing, 1 date fmt) | FAIL (quarantined) | WARN (3/35 = 8.6%) | WARN (1 reject) | PASS | — |

Per platform: google 4 PASS / 2 WARN, linkedin 3 PASS / 2 FAIL, meta 1 PASS / 3 WARN / 1 FAIL.

---

## 6. API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/ingestions` | 201 + run summary; 409 if a run is in progress |
| GET | `/api/v1/ingestions/{run_id}` | 404 on unknown id |
| GET | `/api/v1/metrics` | daily rows **with lineage**; filters platform, campaign, date_from, date_to; limit/offset + total count |
| GET | `/api/v1/metrics/summary` | `group_by=campaign\|platform`; `{filters, totals, groups[]}`; campaign groups keyed by `(platform, campaign)` |
| GET | `/api/v1/deliveries` | `?platform=&health=`; all deliveries including empty slots |
| GET | `/api/v1/deliveries/{delivery_id}` | delivery + every check result + rejected-row samples |
| GET | `/healthz` | liveness, outside `/api/v1` so it is not confused with FR-5 data health |

- CTR = `sum(clicks) / sum(impressions)`, CPC = `sum(spend) / sum(clicks)`: ratios of sums, never averages of
  ratios; `null` when the denominator is 0. Spend to 2 decimals, CTR and CPC to 4 or null.
- An empty result returns **zeroed totals with null CTR and CPC**, never a 404 and never an error. This is the
  only live-reachable demonstration of the brief's named edge case, since no real row has zero clicks
  (minimum is 99) — see findings.md §8.
- **Traceability (NFR-3) runs through `GET /metrics`**, which carries the lineage columns. A campaign row in
  the UI links to `/metrics` pre-filtered to that `(platform, campaign)`, where every contributing delivery id
  and source row number is visible. The README's "tracing a number" section walks one number end to end.
- **Explicit `ORDER BY` on every list endpoint** — metrics by `(platform, campaign, date)` (the PK, a total
  order, safe for offset paging), rejected rows by `source_row`, check results by `check_name`, groups
  deterministic. A full recompute does DELETE then INSERT, so SQLite reuses freed pages and physical order
  changes between runs; without this the live run-it-twice diff fails on ordering alone while every number is
  correct.
- One envelope `{"error": {"code", "message", "details"}}` via handlers for `RequestValidationError`,
  `StarletteHTTPException` (covers 404 on unknown paths and 405) and a catch-all. 400 `date_from > date_to`,
  404 unknown id, 409 concurrent run, 422 invalid enum. FastAPI's defaults are `{"detail": …}` and would
  silently break the claim.
- The ingestion handler is `def`, not `async def`, so the synchronous pipeline runs in the threadpool.
  Otherwise it blocks the event loop for the whole run, the Docker healthcheck stalls, and the 409 branch
  becomes undemonstrable because no second request can be served while the lock is held. Plus WAL and an
  explicit `busy_timeout` at engine creation, `try/finally` on the lock, and `--workers 1` pinned and
  documented. SQLite's single-writer transaction already makes a concurrent run *safe*; the 409 is a UX guard.

---

## 7. Frontend

```
CampaignsPage   Filters, TotalsBar, CampaignTable (sortable), RunIngestionButton
HealthPage      HealthGrid (one cell per SLOT), DeliveryDetail   /health/:platform/:weekStart
api.ts          one typed client, types mirror the API schemas
```

- Filters and sort state in URL search params. Totals always from the API for the active filters, never summed
  in the browser. `—` for a null CTR or CPC.
- **Sorting** (FR-7, "sortable by at least spend and CTR"): client-side over the 13-row grouped summary, nulls
  last so `—` rows sink. The sort key goes in the URL so the view is shareable.
- **Grid cells are slots, not deliveries.** `slot_health = worst(deliveries in slot)`, or missing if none.
  Health is classified per delivery but rendered one cell per slot, so without this the colour of slot
  `(google, 06-15)` — the one cell representing an operational problem — would be undefined. The cell lists
  every file in the slot. Routing by `(platform, weekStart)` rather than a raw file name also avoids
  `/health/linkedin_ads_2026-06-22.json`, which nginx would treat as a static asset.
- Every cell carries a status colour **and** a text label, never colour alone.
- **The empty state explains itself**, naming the quarantined or missing delivery in range and linking to the
  health view. Otherwise the cells the health grid exists to highlight lead to a blank table indistinguishable
  from a broken frontend.
- Run ingestion is a mutation that invalidates the affected queries. Loading, empty and error states on both
  pages.

---

## 8. Repo layout

```
backend/app/config.py        paths, thresholds, period_start / period_end / week_days
backend/app/discovery.py     filename parsing, the expected-slot grid
backend/app/adapters/        base.py, meta_ads.py, google_ads.py, linkedin_ads.py, __init__.py (registry)
backend/app/checks/          base.py, registry.py, row.py, file.py, delivery.py
backend/app/normalize.py     campaign identity resolution
backend/app/pipeline.py      the 8 steps
backend/app/ingest.py        CLI: python -m app.ingest
backend/app/db.py, models.py
backend/app/api/             routers, schemas, errors
backend/tests/
frontend/                    Vite app, Dockerfile, nginx.conf
docs/findings.md, docs/architecture.png, docs/PLAN.md
docker-compose.yml, README.md, NOTES.md, .gitignore
```

`config.py` holds `PERIOD_START = 2026-06-01`, `PERIOD_END = 2026-06-30`, `WEEK_DAYS = 7`; the five weeks are
generated and the last truncates at the period end, so "the last week covers two days" falls out of the rule
instead of being written down. No file name, campaign name, date or expected total is hardcoded anywhere in
pipeline logic or tests.

---

## 9. Docker — Phase 5, built last

`api` (python:3.12-slim, uvicorn `--workers 1`, runs ingestion on startup if the DB is empty and stays up if
that fails) and `web` (multi-stage `node:24-alpine` build → `nginx:alpine` serving the SPA with an
`index.html` fallback and proxying `/api`). `data/` mounted read-only; SQLite on a named volume so
`docker compose down -v` resets it. Healthcheck on `api`, `web` waits for it. `.dockerignore` on both.
`docker compose run --rm api pytest` runs against a temp DB, never the mounted one. The manual non-Docker path
is documented too.

Risk noted: the brief calls compose *"optional, appreciated… do not spend assessment time on it at the expense
of the functional requirements"*, and a node build plus nginx plus a reverse proxy is the longest debug loop in
a build this size. Mitigated by its position last in the phase order. If Phase 5 overruns, fall back to
`vite build` served by uvicorn `StaticFiles`.

---

## 10. Tests — 10, synthetic fixtures only, never asserting totals from the provided data

1. Ingest twice → metrics, check results and health **byte-identical JSON**, not merely equal totals.
2. Adapters: unit conversion, FX direction, epoch → UTC date, each platform's date format.
3. **Timezone:** run the LinkedIn adapter with `TZ=America/New_York` and assert dates are unchanged. The one
   test a synthetic fixture on a UTC box cannot replace.
4. **Precision:** a fixture with a sub-cent micros value and a 3-decimal FX product; assert round-once-at-the-
   aggregate, and that per-row rounding would differ.
5. Error isolation: a truncated or invalid file does not abort the run and is reported.
6. A missing slot and a byte-identical duplicate file are both detected.
7. **Dedupe and PK:** a file with non-adjacent exact duplicates ingests once and does not raise
   `IntegrityError`; the step-6 invariant assert holds.
8. Summary: CTR from sums; CPC null when clicks = 0; an empty filter returns zeroed totals and nulls.
9. API: 404 unknown delivery, 400 `date_from > date_to`, **and a validation 422** all return the envelope.
10. Campaign identity: mixed case plus trailing whitespace collapse to the most common spelling.

---

## 11. Phase plan and done-when

| Phase | Scope | Done when |
|---|---|---|
| 1 | Skeleton, adapters, canonical rows, SQLite schema, idempotent CLI printing row counts and spend totals per platform | Per-file **raw parsed** totals match an independent scratch script (findings.md §10 first table: 403 parsed, 9 parse failures, $536,409.91); two runs print identical output; adapter tests pass |
| 2 | Check framework, all 20 checks, health classification, persisted check results and rejected rows | Every defect in findings.md is attributed to a named check; the **§10 final reference totals** are reproduced (Google $27,954.50 / 150 rows, LinkedIn $5,869.97 / 64, Meta $14,884.55 / 110, total $48,709.02 / 324); health distribution is **8 PASS / 5 WARN / 3 FAIL**; idempotency and error-isolation tests pass |
| 3 | API and its tests | Every endpoint works at `/docs`; the three empty-result filters from findings.md §8 return zeroed totals with nulls; API tests pass |
| 4 | Frontend | Both pages work end to end, including Run ingestion, sorting, and the loading / empty / error states; the red cells drill through to a self-explaining empty table |
| 5 | Docker | `docker compose up --build` from a fresh clone serves a working app at http://localhost:8080 with data; tests pass in the container |
| 6 | README and final checks | README written; `docs/architecture.png` compared against the code as built with every mismatch listed; repo cloned to a temp folder and the README followed exactly, both paths |

The reference totals are a **Phase 2** target, not a Phase 1 one, because they depend on dedupe, validity
rejection and quarantine — all of which are check decisions that do not exist until Phase 2. Phase 1's target
is what the adapters alone produce.

`metrics` is therefore not populated until Phase 2: its primary key is only safe after step 6, and inserting
the 403 raw parsed rows would raise `UNIQUE constraint failed` and roll back the run. Phase 1 creates the full
schema and persists `deliveries` and `ingestion_runs`, whose keys are unique by construction.

**Never adjust a check to hit a target count.** If a count disagrees with this plan, the plan text is what gets
corrected.

---

## 12. Environment

| Tool | Found | Consequence |
|---|---|---|
| `python3` | 3.11.6 | not the 3.12 in the stack; avoid 3.12-only syntax |
| `python3.12` | 3.12.0 at `/usr/local/bin/python3.12` | manual path uses `python3.12 -m venv .venv`; nothing installed globally |
| global site-packages | fastapi, pydantic, sqlalchemy, uvicorn, pandas present; pytest absent | all installs go in `.venv`; the README says so, or a reader will mistake the global ones for the dependency story |
| node / npm | 25.6.1 / 11.9.0 | fine for Vite; Docker pins `node:24-alpine` |
| docker / compose | 29.2.1 / v5.1.0 | fine |
| git | 2.40.1, repo initialised on `main` | section 7 of the brief requires a git repository |

`.gitignore` covers `.venv/`, `node_modules/`, `dist/`, `__pycache__/`, `*.db`, `.DS_Store`. `data/` stays
tracked and untouched. Commits land in logical slices so the live session can be walked through by commit.

---

## 13. Changes from the original brief-to-self

**Agreed in Phase 0 review:** sortable campaign table (FR-7, a hard requirement the original plan omitted) ·
`canonical_key_unique_across_deliveries` · ordered per-platform date-format list instead of format inference,
with `date_within_delivery_week` as the safety net · one CPM-ratio check plus one rows-per-day check instead of
a single vague volume check · weeks derived from three config values · liveness moved to `/healthz` · explicit
FastAPI exception handlers · the scale check reports the inferred factor and the alternative total ·
`fail_rate` computed rather than stored · row checks collect all failing reasons instead of short-circuiting.

**Added after the adversarial audit, each independently verified:** the §1 precision contract · the `drop_row`
action plus the in-memory key collapse and invariant assert · health as an ordered precedence list with
`rows_suppressed` split from `rows_rejected` · errored checks inherit their declared severity · explicit
`ORDER BY` everywhere plus a byte-equal idempotency test · `raw_spend_unit` and the nullable `raw_campaign` /
`raw_date` columns · slot-keyed health grid and `/health/:platform/:weekStart` routing · sync handler, WAL,
`busy_timeout`, `--workers 1` · self-explaining empty state · the `campaign_day_coverage` check · discovery
skips dotfiles · F1 described as factor exactly 100 with the ratio as detection signal only.

**Considered and not adopted:** quarantining the defective *column* of `meta_ads_2026-06-08.csv` rather than
the file. The argument for it is quantitative — whole-file quarantine discards 1,403,288 impressions and 29,241
clicks for which there is no evidence of a problem — but a nullable `spend_usd` breaks FR-1's canonical schema
and complicates every aggregation. It is one branch in one check and remains reversible. Both totals are
published either way.

**Corrections made to the audit's own findings:** its "mixed line endings" data defect was downgraded to a
coding rule, since Python's `csv` module handles the CRLF files correctly and the stray `\r` appears only with
manual splitting; its claim that per-day volume sits within ±11% holds on raw rows but not on accepted rows
(0.762–1.029); its timezone framing double-counted 3 rows inside a set of 12; and its figure for the duplicate
rows' spend ($1,418.65) was wrong — the surplus is **$1,299.61**, which is what makes Google reconcile exactly
to $27,954.50.
