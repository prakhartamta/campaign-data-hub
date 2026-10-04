# Technical Assessment — Campaign Data Hub

**Role:** Full-Stack Engineer
**Estimated effort:** 4–5 hours
**Stack:** Python 3.12+ / FastAPI · React + TypeScript

## 1. Background

Our marketing organization runs paid campaigns on several advertising
platforms. Each platform delivers a weekly export file in its own format, and
these deliveries are ingested into a central reporting system. Two problems
exist today:

1. Nobody trusts the aggregated numbers, because each platform reports in
   different schemas, date formats, currencies, and units.
2. Nobody notices when a delivery arrives broken — malformed rows, duplicated
   files, or missing deliveries surface only weeks later as "the dashboard
   looks wrong."

You are asked to build the first version of the **Campaign Data Hub**: a
system that (a) normalizes all deliveries into one consistent dataset and
(b) assesses the quality of every delivery it ingests, so that both the
numbers and their trustworthiness are visible in one place.

## 2. Provided materials

`data/deliveries/` contains 15 weekly delivery files covering June 2026.
Each platform is expected to deliver **one file per week** (weeks starting
06-01, 06-08, 06-15, 06-22, and 06-29 — the last covers two days).

| Platform | Format | File pattern |
|---|---|---|
| Meta Ads | CSV | `meta_ads_<week-start>.csv` |
| Google Ads | CSV | `google_ads_<week-start>.csv` |
| LinkedIn Ads | JSON | `linkedin_ads_<week-start>.json` |

`data/exchange_rates.json` provides fixed currency conversion rates supplied
by the finance team.

These files are representative of real platform exports. Schemas, date
formats, currencies, and units differ between platforms, and the deliveries
are **not** clean: expect row-level defects, file-level defects, and
delivery-level defects. Identifying them is part of the assessment — we will
not enumerate them for you.

## 3. Functional requirements

### 3.1 Ingestion pipeline (Python)

- **FR-1** — Ingest all delivery files and normalize them into a single
  canonical dataset containing, at minimum: `platform`, `campaign`, `date`,
  `spend_usd`, `impressions`, `clicks`.
- **FR-2** — For every delivery processed, produce and persist a
  **structured quality report**: which checks ran, their outcome, and
  sufficient detail to answer *"what exactly is wrong with this delivery and
  how badly?"*. The set of checks is yours to design; consider what can go
  wrong at row, file, and delivery level (completeness, validity,
  duplication, volume, cadence, …).
- **FR-3** — Each delivery must receive an overall health classification
  (e.g. pass / warn / fail — the definition and thresholds are yours to
  design and document).

### 3.2 API (FastAPI)

- **FR-4** — Campaign metrics: list normalized metrics with filters for
  platform and date range; provide totals and derived metrics (CTR =
  clicks / impressions, CPC = spend / clicks) grouped by campaign and by
  platform.
- **FR-5** — Data health: list all deliveries with their health
  classification; retrieve the detailed quality report for a single delivery.
- **FR-6** — Trigger ingestion (initial or re-ingestion) via the API.

Endpoint design — naming, resource shapes, status codes, error bodies — is
part of what we assess.

### 3.3 Frontend (React + TypeScript)

- **FR-7** — A **campaign metrics view**: a table of campaigns showing spend
  (USD), impressions, clicks, CTR, and CPC; sortable by at least spend and
  CTR; filterable by platform and date range; with a totals summary that
  reflects the active filters.
- **FR-8** — A **data health view**: all deliveries with their health status,
  visually scannable so a reviewer spots problem deliveries at a glance, with
  a drill-down showing each check's outcome and failure details for a
  selected delivery.

Visual polish is not assessed; clarity and correct behavior are.

## 4. Non-functional requirements

- **NFR-1 (Idempotency)** — Re-ingesting the same delivery, or re-running the
  full pipeline, must not duplicate metrics or quality results and must yield
  the same outcome. *We test this live by running your ingestion twice.*
- **NFR-2 (Error isolation)** — A malformed row, file, or delivery must never
  abort the run. It is recorded in the quality report and processing
  continues.
- **NFR-3 (Traceability)** — For any number shown in the UI, you should be
  able to explain which deliveries and which transformation rules produced it.

## 5. Constraints

- **Storage:** your choice — PostgreSQL (e.g. via Docker) and SQLite are both
  natural fits; DuckDB or in-memory are acceptable. Justify your selection in
  the README.
- **Libraries:** any reasonable choices (pandas, polars, SQLAlchemy, chart
  libraries, …).
- **Scope discipline:** we do not expect a complete product in the allotted
  time. Prioritize deliberately and record what you deferred; the *"what I
  would do with more time"* section of your README is weighted in the
  evaluation.

## 6. Evaluation criteria

1. **Correctness of the normalized numbers** — we know what they should be.
2. **Quality-check coverage and design** — which defects your checks caught
   (we planted a specific set), and whether a teammate could add a new check
   without refactoring.
3. **Idempotency and error isolation** — verified live, not taken on trust.
4. **API design** — resource modeling, naming, error behavior, edge cases
   (e.g. CPC when clicks = 0).
5. **Frontend** — end-to-end functionality, sane state management, readable
   component code.
6. **Engineering communication** — README quality (setup, findings,
   decisions, trade-offs, deferred work) and whether the architecture diagram
   matches the code as built.

## 7. Submission

Provide a git repository (link or archive) containing:

- All source code.
- An **architecture diagram** (required): one diagram showing the system's
  components — deliveries, pipeline, storage, API, frontend — and how data
  flows between them. Any format is acceptable (hand drawing, diagrams.net,
  Mermaid, Excalidraw, …); we assess the thinking, not the tooling. Be
  prepared to walk through it in the live session.
- A README covering: setup and run instructions (backend, frontend,
  ingestion), the quality checks you implemented and what they found in the
  provided data, your key design decisions and trade-offs, and what you would
  do with more time.
- Tests where they add signal — a few well-chosen tests are worth more than
  exhaustive coverage.
- **Optional, appreciated:** a `docker-compose.yml` that brings the whole
  project up with one command. Not mandatory — do not spend assessment time
  on it at the expense of the functional requirements.

Your submission must run from a fresh clone by following your README alone.

## 8. Accountability for your submission

Every part of your submission is treated as your own work. During the live
session you will be asked to explain, justify, and modify **any** part of it
— architecture, pipeline logic, API design, or frontend code. Whatever tools
you used to produce it, code you cannot reason about counts against you, not
for you.
