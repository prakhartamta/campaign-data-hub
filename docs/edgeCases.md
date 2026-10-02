# Edge cases

Every edge case this design handles, why it matters, and where in the code it lives. Written as
a revision sheet: the question first, then the shortest true answer.

Status key, and it matters that these are different things:

* **done** — the code exists today and the behaviour was verified by running it.
* **planned** — the decision is made and recorded, but the module that implements it is not
  written yet. A reviewer asking "show me" would find nothing.
* **guard** — implemented, correct, and never fires on the provided data. Kept deliberately.
* **not planned** — deliberately out of scope.

**Implemented so far** (Phase 1, in progress): `config.py`, `money.py`, `adapters/base.py`,
`discovery.py`. Everything tagged **planned** below belongs to a module that does not exist yet.
Do not claim a planned item as working.

---

## 1. Dates and time

### A naive epoch conversion is wrong on half the planet — planned
`datetime.fromtimestamp(ms / 1000)` without a timezone reads the host's local zone. All 23
LinkedIn timestamps are exactly UTC midnight, so on any UTC-negative host every date moves back
one day: `2026-06-01` becomes `2026-05-31`, outside the reporting period. The date-in-week rule
then turns an off-by-one into *deleted data* — 12 rows, $1,042.74, all four LinkedIn deliveries
flipped to FAIL.

It is correct in IST and wrong in New York, so it cannot be caught by testing on one machine.
Fix: `datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()`. Pinned by a test that sets
`TZ=America/New_York`.

### LinkedIn switches from milliseconds to seconds — planned (and silent by nature)
Nothing raises. `1780272000 / 1000` is a valid date: **1970-01-21**. `parse_date` never sees it,
because `date_ts` is an integer and never reaches `strptime`. It is caught one stage later by
`date_within_delivery_week`, which rejects all 21 rows and FAILs the delivery at 100%.

This is the clearest argument for keeping that check: a unit error in a *numeric* date field is
invisible at parse time by construction. Worth adding `assert ts % 86_400_000 == 0` in the
LinkedIn adapter so it is caught where it happens rather than three stages downstream.

### `03/04/2026` — is that March 4 or April 3? — done (mechanism), planned (per-adapter formats)
Per-platform ordered formats, no inference. Meta declares `("%m/%d/%Y", "%Y-%m-%d")`, primary
first. A value matching none of them is rejected with a reason naming the value and every format
tried: `13/06/2026 matches none of meta_ads formats: %m/%d/%Y, %Y-%m-%d`.

*How do you know it is not DD/MM?* Two independent answers. From the data: 91 Meta rows have a
second component greater than 12, impossible as a month. From the design: a wrong declaration is
self-exposing, because under DD/MM a date like `06/02/2026` reads as 6 February, falls outside
the delivery week, and the date-in-week check lights up every row in the file.

Deliberately **not** a permissive date parser. Reading `13/06/2026` as 13 June in a MM/DD feed
would invent a date, and in a data-quality tool a silent guess is the bug, not the fix.
`adapters/base.py` → `parse_date`.

### A date that does not exist — done (rejected), planned (coverage wording)
`06/31/2026`: June has 30 days, so `strptime` rejects it under every format. Becomes a
`ParseFailure`, not a canonical row.

Second-order effect the report must state: `App Install Push` then has 6 of 7 days and is missing
`06-01` entirely. The file's day set is `{1..7, 31}` and that campaign's block runs `31,2,3,4,5,6,7`
while every other block starts at `01` — so `01` was almost certainly corrupted into `31`. Still
reject, never guess, but say *"App Install Push lost 2026-06-01"* rather than *"one invalid date"*.

### The last week is only 2 days — done
The brief says the 06-29 week covers two days. Raw row counts for that week look like a
collapse: Google 10 vs 35, i.e. 0.29x. Any volume check on raw counts FAILs all three final-week
deliveries on perfectly clean data (Google −71.8%, Meta −63.4%, LinkedIn −70.3%).

Fix is per-covered-day normalisation. `config.Week.days_covered` returns 2 for that window, and
`expected_weeks()` truncates the last window at `PERIOD_END` — so "the last week is short" falls
out of the rule instead of being a special case.

### A delivery arrives late — done by construction
The slot grid is regenerated from config on **every run**, not persisted from a previous one. So a
late file simply flips its slot from MISSING to present on the next recompute; no migration, no
special case. Nothing currently records *lateness* — the only available signal would be file
mtime, which is unreliable because copying or cloning resets it.

---

## 2. Money and precision

### Rounding per row loses a cent — done
Two places in this dataset punish it, both invisible unless you look:

```
Google   exact 27,954.499999   round-half-up 27,954.50   truncate / micros//10000  27,954.49
LinkedIn exact  5,869.9728     round once     5,869.97   round each row then sum    5,869.96
```

The Google total sits on a half-cent boundary because of one row: `google_ads_2026-06-15.csv`
line 17, `64629999` micros — the only value in 193 Google rows that is not a multiple of 10,000.
The LinkedIn drift is pure accumulation across 63 rows, so **no rounding mode fixes it**; only
rounding once does.

Consequence for the schema: spend is an integer count of micro-USD, and `micros_to_usd` is called
once, at the API boundary. A `NUMERIC(12,2)` column or a `round(x, 2)` in a normalizer would
force per-row rounding and publish $48,709.01 instead of $48,709.02. `money.py`.

### `Decimal(1.08)` is not 1.08 — done
`json.load` decodes the rate to a float, and `Decimal(1.08)` is
`1.0800000000000000710542735760100185871124267578125`. Rates are built with `Decimal(str(rate))`.
`money.load_rates`.

### The rates file is not a bare rate map — done
Top-level keys are `['comment', 'rates']`. Iterating the top level would treat `comment` as a
currency with a string rate. Read `document["rates"]`. `money.load_rates`.

### Which way does the rate go? — done
The file states its own direction: *"Fixed rates to USD. 1 unit of currency = N USD."* So
conversion **multiplies**. Nothing about the magnitudes would reveal this — EUR at 1.08 gives
per-row medians of 81.85–109.65 and at 1/1.08 gives 70.2–94.0, both plausible beside the other
platforms. The comment is the only evidence and it is authoritative.

*If finance flips the direction:* `money.py` line 66 is the only line that applies a rate. But
`fx_rate` is stored on every row as lineage, so the stored column's **meaning** changes too — the
README normalization table and the `load_rates` docstring have to change with it or the lineage
starts lying.

### A new currency needs more than 6 decimals — done, loudly
`to_micros_usd` raises rather than silently truncating. Micro-USD is lossless for this data (EUR
amounts have 2 decimals, the rate has 2, so USD has at most 4), and the assertion says so out
loud instead of letting a future currency lose a fraction of a cent.

### Spend reported in the wrong unit — planned (Phase 2 check)
`meta_ads_2026-06-08.csv` reports cents in a dollar field. The factor is **exactly 100**.

The decisive evidence is not a ratio — it is that Meta's weekly totals line up once divided:
`4,452.87 / 4,800.70 / 4,392.38 / 4,338.20 / 1,589.69`. Supporting: all 35 values are whole
dollars against 0 of 114 elsewhere; median CPM 355 against 3.09–3.91.

**Do not quote "~104x" as the factor.** The median-spend ratio gives 104.08, median CPC gives
114.16, median CPM gives 102.96 — three mutually inconsistent numbers, because each compares
different row populations. The ratio is the *detection signal*; 100 is the factor.

Handling: quarantine the delivery, 0 rows, FAIL, and report the inferred factor plus the
$4,800.70 it would have contributed. Never rewrite reported money on an inference. The cost is
stated rather than hidden: it also discards 1,403,288 impressions and 29,241 clicks that are
fine. The alternative total ($53,509.72) is published too, computed by the pipeline.

### Why CPM and not spend for the scale check — planned (threshold in config, check in Phase 2)
Spend changes legitimately with volume and with week length. CPM is a *rate*, so it is flat
regardless, which isolates "the money is wrong" from "the week was quiet". Clean deliveries sit
within 1.2x of their platform baseline; the defect is 103x. The threshold of 10 sits in the empty
space between — move it to 3 or to 50 and the outcome is identical, which is the point.

---

## 3. Parsing and file structure

### CRLF files and a stray `\r` — planned (rule for the adapters)
All 10 CSVs are CRLF. With `newline=''` and a manual `split(',')`, the last field of every row
carries a trailing `\r` — so an empty `clicks` field becomes `'\r'`, and both `field == ''` and
`not field` are False. The three genuinely-empty-clicks rows would be misreported as unreadable
values instead of missing ones.

`cut -d, -f5` and `awk -F,` have the same problem, so ad-hoc shell QA of these files is
unreliable. Python's `csv` module is clean either way; all parsing goes through it.

### A thousands separator in a money field — planned, and the reason string needs the ragged-row case
Two different failures depending on quoting:

```
"1,200.50"  quoted    -> Decimal('1,200.50') -> InvalidOperation [ConversionSyntax]
 1,200.50   unquoted  -> an extra CSV column
```

The unquoted case is the interesting one. The columns shift:

```
{'spend_usd': '1', 'impressions': '200.50', 'clicks': '37215', None: ['574']}
```

`Decimal('1')` succeeds, so the row does **not** die on spend — it dies on `int('200.50')`. The
quality report would say *"impressions is not an integer"* for what is really a ragged row.

**Open:** `file_structure_valid` should detect the overflow, which `csv.DictReader` hands back
under the `None` key, and report a column-count mismatch instead.

### `Decimal('')` is not a `ValueError` — planned (rule for the adapters)
```
Decimal('')    -> decimal.InvalidOperation  (subclasses ArithmeticError, NOT ValueError)
Decimal(None)  -> TypeError
int('')        -> ValueError
```
A parser written `except ValueError` catches an empty *clicks* field but lets an empty *spend*
field escape as an unhandled exception, where it becomes `status="error"` instead of a correctly
classified rejection. Parsing catches `(ValueError, ArithmeticError, TypeError)`.

### A missing required column — planned (guard)
The adapter returns `ParseResult(rows=[], failures=[], missing_fields=[...])`. Non-empty
`missing_fields` means the file is structurally wrong rather than dirty, and
`file_structure_valid` quarantines the delivery: 0 rows, FAIL.

### Meta has no currency column at all — planned, as a documented assumption
USD is implied solely by the header name `spend_usd`. So `currency_in_rates_file` **structurally
cannot cover one of the three platforms** — "it does not fire" is true for a different reason
there. USD-for-Meta is documented as an assumption, not presented as a passed check.

### `.DS_Store` in the data directory — done
`data/.DS_Store` exists. `glob` skips dotfiles, but `os.listdir`, `os.walk` and `Path.iterdir`
all return it, and opening it raises `UnicodeDecodeError` at byte 3131. Without an explicit skip
the delivery count would be 16 on a Mac and 15 on a reviewer's Linux box, and the findings table
would stop matching the output. `discovery.list_candidate_files` skips dotfiles and filters on
`DELIVERY_EXTENSIONS`.

### Scanning subdirectories — not planned (out of scope)
`directory.rglob("*")` is the one line. Two things break with it:
1. `path.name.startswith(".")` only guards the *file* name, so `deliveries/.cache/x.csv` would
   pass. Needs `any(part.startswith(".") for part in relative.parts)`.
2. `delivery_id = path.name` would collide across folders, and `delivery_id` is the `deliveries`
   primary key. It would have to become the relative path.

---

## 4. Identity and keys

### The same campaign under three different spellings — planned (pipeline step 5)
`brand awareness q2` appears as `Brand Awareness Q2` (x27), `brand awareness q2` (x1) and
`Brand Awareness Q2  ` (x2), across **two files**. Case-folding alone or trimming alone still
leaves it split into two rows in the metrics view — both operations are needed before grouping.
18 distinct raw strings collapse to 13 canonical campaigns.

Resolution: trim, group case-insensitively, display the most common spelling, tie broken by
`(count desc, spelling asc)` so the primary key is deterministic across runs. Never `.title()` —
it would turn `Retargeting - US` into `Retargeting - Us`.

This is a **cross-delivery** decision, so it cannot happen inside per-file processing: the vote
spans files. It is pipeline step 5, after per-file work and before the key is built.

### Campaign identity becomes global instead of per-platform — would break the PK
`CanonicalRow.key` is `(platform, campaign, date)`. Drop `platform` and Meta's `Summer Sale` on
2026-06-01 collides with Google's. The `metrics` primary key rejects the second row, and because
the recompute is one transaction, **the entire run rolls back** — 0 rows, no quality report
explaining why.

The design question underneath: global identity could mean *sum across platforms* (needs a
different table grain, and loses the per-platform breakdown FR-4 asks for) or *collide* (a bug).
`adapters/base.py` → `CanonicalRow.key`, plus the `metrics` PK and the summary grouping.

### 8 duplicate rows inside one file — planned (Phase 2 check)
`google_ads_2026-06-01.csv` has 43 rows, 35 distinct. **No duplicate pair is adjacent** — the
line gaps are 23, 7, 29, 35, 18, 20, 12, 4. Any neighbour-comparison or streaming dedupe finds
zero of them; full-row hashing across the whole file is required.

It is also the only one of 15 deliveries whose rows are not grouped by campaign (35 campaign runs
for 5 campaigns, fully shuffled). That shuffle is itself a signal, and it is why check samples
are explicitly sorted rather than left in read order.

Surplus: 8 rows, $1,299.61, 445,773 impressions, 8,832 clicks. Removing them is what makes Google
reconcile exactly: `35,696.80 − 6,442.69 (resend) − 1,299.61 = 27,954.50`.

### The same key from two different deliveries — planned (guard)
Two accepted deliveries producing the same `(platform, campaign, date)` would violate the metrics
PK and abort the whole transaction, which is exactly what NFR-2 forbids. Resolved deterministically
by rejecting all colliding copies and flagging. Zero collisions occur in this data; the check is
what makes the PK safe. `canonical_key_unique_across_deliveries`.

### Why the key collapse happens in memory — planned (pipeline step 6)
The check framework's actions are reject / quarantine / flag — none of which *removes* a row. So
"keep one duplicate, flag it" needed a fourth action, `drop_row`, plus an in-memory collapse into
a dict keyed by `(platform, campaign, date)` **before** any INSERT, with
`assert len(dict) == rows_accepted` after it. Without that, a future collision surfaces as an
`IntegrityError` that silently nukes the run instead of a loud invariant failure.

---

## 5. Delivery and slot resolution

### Two files in one slot: duplicate or conflict? — done (detection), planned (resolution)
Same names, opposite verdicts:

- **Duplicate** (byte-identical): harmless. Count once, copy ingests 0 rows, **WARN**.
- **Conflict** (different contents): two files claim the same week and disagree. Never pick one
  silently. **FAIL** and make a human decide.

Discovery cannot tell them apart. It inspects names and the filesystem only — no `read_bytes`,
no `hashlib`. The name `google_ads_2026-06-15_resend.csv` looks identical either way. The missing
information is the **content hash**.

So: discovery reports *that* a slot is doubled (step 1); step 2 reads the bytes anyway to parse
them, so hashing is free there; step 3 compares hashes within the slot and decides. Here both are
`4dd8a017b6e4694b…`, so it resolves as a duplicate. The conflict branch is tested but never fires.

Why the distinction earns its code: collapse the two cases and the day a genuine correction
arrives you discard it, keep stale numbers, and report WARN on a slot whose totals are wrong —
the exact *"nobody notices when a delivery arrives broken"* failure the brief opens with.

### Which of two files is the original? — planned (pipeline step 3)
The one matching the naming convention. `google_ads_2026-06-15.csv` wins over
`google_ads_2026-06-15_resend.csv`. If neither matches, first by sorted name, so the choice is
deterministic rather than filesystem-order dependent.

### A delivery that never arrived — done (detection), planned (check message)
`linkedin_ads_2026-06-22.json`. The grid is built from config, not from the directory listing, so
the slot exists with zero files and becomes a FAIL record with its expected filename. The check
reports the expected row count (3 campaigns x 7 days = 21). The dollar magnitude (~$1,900,
~580,000 impressions, roughly a quarter of LinkedIn's month) is a neighbouring-week extrapolation,
so it belongs in the README findings, not inside a check that cannot know it.

### A file whose name has junk appended — done
```
..._resend.csv       -> ('meta_ads', 2026-06-01, True)   correct
... (1).csv          -> ('meta_ads', None, False)        WRONG: the week IS readable
...-copy.csv         -> ('meta_ads', None, False)        WRONG
....final.csv        -> ('meta_ads', None, False)        WRONG
```
**Open bug.** `parse_delivery_name` splits the remainder on `_`, so only underscore-separated
suffixes are recognised. The single most common real-world duplicate pattern — a browser or
Finder appending ` (1)` — is FAILed as "unreadable week" instead of being processed with a naming
flag. Fix: read the ISO date off the front of the remainder and treat whatever follows as the
suffix, whatever the separator.

### A file from a platform we do not know — done (guard)
`tiktok_ads_2026-06-01.csv` returns `(None, None, False)` and lands in `DiscoveryResult.unplaced`.
Recorded as unrecognized, FAIL, and never allowed to stop the run.

### A known platform with an unreadable week — done (guard)
`meta_ads_june.csv` returns `('meta_ads', None, False)`. Without a week there is no window to
validate dates against, so it is unplaced and FAILs rather than being processed against a guessed
window.

### A platform named as a prefix of another — done
With platforms `["meta", "meta_ads"]`, the file `meta_ads_2026-06-01.csv` must resolve to
`meta_ads`, not to `meta` with a week of `ads_2026-06-01`. One
`sorted(known_platforms, key=len, reverse=True)` prevents a whole class of silent misattribution.

### Cadence changes to twice a week — done (verified both models)
Two readings, and only one of them breaks anything:

- **Two shorter windows** (Mon–Wed, Thu–Sun): change `WEEK_DAYS` in config. Nothing in
  `discovery.py` changes — `build_slots` is already the product of platforms and whatever the
  schedule yields, and the window starts differ so expected filenames stay distinct. Verified at
  `WEEK_DAYS=3`: 5 distinct filenames out of 5.
- **Two files inside one 7-day window**: now `expected_filename` collides, because it is built
  from `week.start` alone. Both slots would expect `meta_ads_2026-06-01.csv`. The fix is a part
  number in the filename convention, changed in `expected_filename` and `parse_delivery_name`
  together, since those two must never drift apart.

---

## 6. Health classification

### The reject-rate rule contradicts the duplicate rules — planned (Phase 2)
As originally written the rules disagreed on 2 of 15 deliveries:

- `google_ads_2026-06-01.csv`: 8 dropped duplicates / 43 = 18.6% > 10% → FAIL, although the file
  is a textbook-perfect 35 rows after dedupe.
- the resend: 0 accepted of 35 = 100% → FAIL, although the policy promises WARN.

Two fixes, both needed. **Split the counters:** `rows_rejected` counts only row-level validity
failures; `rows_suppressed` counts rows removed by a file- or delivery-level action (dedupe,
duplicate file, quarantine). Only `rows_rejected` feeds the rate. **Make health an ordered
precedence list** rather than an OR of conditions, so "missing" and "quarantined" are decided
before any rate is consulted.

Invariant: `rows_total = rows_accepted + rows_rejected + rows_suppressed`.

### A check that crashes leaves the delivery green — planned (Phase 2)
Health was defined on checks that *failed*. `status="error"` is neither pass nor fail, so a
crashed check produced a PASS delivery with a hidden red check — reintroducing the brief's
opening failure through the mechanism meant to prevent it. **An errored check inherits its
declared severity**, so an errored fail-severity check FAILs the delivery.

### Row-level statistical checks are not viable — measured, applied in Phase 2
Natural per-campaign day-to-day variance is huge: CTR spans 4.3x, CPC spans 8.5x ($0.070–$0.597),
clicks 99–4,191. False positives against each campaign's own median:

| tolerance | impressions | clicks | spend | CTR | CPC |
|---|---|---|---|---|---|
| ±50% | 85 | 163 | 26 | 121 | 148 |
| ±100% | 13 | 64 | 0 | 31 | 44 |
| ±200% | 0 | 7 | 0 | 0 | 3 |

A row-level median-ratio check must be looser than 3x to be clean, at which point it catches the
100x cents defect and nothing else. So **row-level checks are plausibility bounds only** (real
calendar date, spend >= 0, clicks <= impressions, date inside the week, currency known) and
statistics live at file and delivery aggregate level.

### Where the volume band comes from — measured, threshold in config, check in Phase 2
Accepted rows per covered day, relative to the platform's other deliveries. Observed range
0.762–1.029, the minimum being `linkedin_ads_2026-06-08.json` after its 5 rejections. The
`[0.5, 2.0]` band leaves about 1.5x of margin. WARN, not FAIL, because a volume change can be
legitimate — a campaign genuinely paused.

---

## 7. API and UI edges

### CPC when clicks = 0 — unreachable from the real data (primitives done)
Minimum clicks on any accepted row is **99**; minimum impressions **7,221**; zero rows have a
zero in either column. No campaign group on any filter can produce a zero denominator from real
values.

The only live-reachable zero denominator is an **empty result set** — so the empty state *is* the
demo of this named edge case. `ratio()` and `cost_ratio()` return None rather than 0, because
reporting `0.0000` for no clicks reads as "clicks are free".

### The quality policy manufactures empty result sets — planned (Phase 3 and 4)
On exactly the filters a reviewer reaches for after clicking the red cells:

| Filter | rows |
|---|---|
| `platform=meta_ads`, `06-08`–`06-14` (quarantined) | 0 |
| `platform=linkedin_ads`, `06-22`–`06-28` (missing) | 0 |
| `platform=linkedin_ads`, `date=2026-06-14` (all rows rejected) | 0 |

All three return zeroed totals with null CTR and CPC — never a 404, never an error. And the UI
must say *why* it is empty, naming the quarantined or missing delivery, or the two cells the
health grid exists to highlight lead to a blank table indistinguishable from a broken frontend.

### An entire calendar day disappears — planned (Phase 2 check)
`linkedin_ads_2026-06-08.json` indices 6, 13 and 20 are all `2026-06-14`, one per campaign, and
all three are in the reject set. So **LinkedIn has no data for 2026-06-14 at all**. Final day
coverage: Google 30/30, Meta 30/30, LinkedIn 22/30.

*"LinkedIn has no data for 2026-06-14"* is a strictly more legible statement than *"5 rows
rejected"*, and it is the one a stakeholder notices first. That is what `campaign_day_coverage`
reports.

### Two runs differ with every number correct — planned (Phase 3)
A full recompute does DELETE then INSERT, so SQLite reuses freed pages and physical row order
changes between runs. Without an explicit `ORDER BY`, `limit`/`offset` paging can repeat or skip
rows within one run, and two runs can return the same rows in a different JSON order. The live
idempotency diff then fails on **ordering alone** while every figure is right.

Fix: `ORDER BY` on every list endpoint — metrics by `(platform, campaign, date)` which is the PK
and therefore a total order, rejected rows by `source_row`, check results by `check_name`. The
idempotency test asserts byte-equal JSON, not merely equal totals.

### Raw lineage without a unit is unreadable — done (model), planned (surfaced in API)
Google's raw spend is micros, Meta's is dollars, LinkedIn's is EUR units. One `raw_spend` column
with no unit renders `$117,410,000` beside a normalized `$117.41`. Hence `raw_spend_unit`. And
`raw_campaign` / `raw_date` are populated only when normalization changed the value, which is
what makes a normalization *demonstrable* rather than merely claimed.

### FastAPI's own error bodies bypass the envelope — planned (Phase 3)
`date_from=2026-13-01` or `limit=abc` is rejected by Pydantic *before* the handler runs and
returns `{"detail": [...]}`, not the envelope. `HTTPException(404)` likewise. These are the first
two things a reviewer types. Handlers are registered for `RequestValidationError`,
`StarletteHTTPException` (which also covers 404 on unknown paths and 405) and a catch-all.

### A synchronous recompute inside an async handler — planned (Phase 3)
If `POST /ingestions` were `async def` with a synchronous pipeline, it would block the event loop
for the whole run: the Docker healthcheck stalls, and the documented 409 branch becomes
**undemonstrable**, because no second request can be served while the lock is held. The handler is
`def` so Starlette runs it in the threadpool. Plus WAL and an explicit `busy_timeout`, since
TanStack Query fires `GET /metrics` the instant the mutation resolves and would contend with the
writer.

### The health grid cell with two files has no defined colour — planned (Phase 4)
The grid is one cell per **slot**, but health is classified per **delivery**. Slot
`(google, 06-15)` holds a PASS original and a WARN resend, so the one cell on the board that
represents an operational problem had undefined rendering. `slot_health = worst(deliveries in
slot)`, or missing if none, and the cell lists every file in it.

### `/health/linkedin_ads_2026-06-22.json` looks like a static asset — planned (Phase 4)
A SPA route ending in `.json` is what nginx would try to serve from disk. Routing by
`(platform, weekStart)` instead of a raw file name avoids it, and fixes the undefined cell colour
above at the same time.

### Concurrent ingestion runs — planned (Phase 3), with an honest limit
409 via an in-process lock, acquired in `try/finally`. Worth knowing for the live session:
SQLite's single-writer transaction already makes a concurrent run *safe* — it would serialise, not
interleave — so the 409 is a UX guard rather than a correctness one. The lock is per-process, which
is why uvicorn is pinned to `--workers 1` and the limit is documented.

---

## 8. Extending the system

Questions of the form *"where would you change X?"* and the minimum set of files.

| Change | Where |
|---|---|
| New platform, same file type | New `app/adapters/<platform>.py`; register it in `app/adapters/__init__.py`. Two files. |
| New platform delivering `.tsv` | The above, plus `.tsv` in `DELIVERY_EXTENSIONS` (config.py). The adapter must pass `delimiter="\t"` to `csv.DictReader`, which defaults to a comma. |
| New quality check | One new class in `app/checks/{row,file,delivery}.py`, registered. Nothing else. |
| A threshold | One constant in `config.py`. Nothing depends on the value. |
| FX direction | `money.py` line 66, plus the lineage meaning and the README table. |
| Delivery cadence | `WEEK_DAYS` in config.py, if the model is shorter windows. |
| Date format for a platform | That adapter's `DATE_FORMATS` tuple, primary first. |
| Campaign identity rule | `CanonicalRow.key`, the `metrics` PK, and the summary grouping — together. |
| Reporting period | `PERIOD_START` / `PERIOD_END` in config.py. The week grid and the short final week follow. |

---

## 9. The trace, for the "walk me through it" question

`meta_ads_2026-06-01.csv` line 2 — `Summer Sale,06/01/2026,200.08,37215,574`:

| # | Where | Value out |
|---|---|---|
| 1 | `discovery.discover` | entry |
| 2 | `config.expected_weeks` | 5 windows, last `days_covered=2` |
| 3 | `discovery.build_slots` | 15 empty slots; this one expects `meta_ads_2026-06-01.csv` |
| 4 | `discovery.list_candidate_files` | 15 paths, `.DS_Store` excluded |
| 5 | `discovery.parse_delivery_name` | `('meta_ads', date(2026,6,1), False)` |
| 6 | `discovery.DiscoveredFile` | `delivery_id='meta_ads_2026-06-01.csv'` |
| 7 | `money.load_rates` | `{'USD': Decimal('1.0'), 'EUR': Decimal('1.08')}` |
| 8 | `csv.DictReader` | `{'campaign_name': 'Summer Sale', 'date': '06/01/2026', ...}`, no stray `\r` |
| 9 | `base.parse_date` | `(date(2026,6,1), False)` — primary format, no normalization flag |
| 10 | `money.to_micros_usd` | `200080000`, an `int` |
| 11 | `base.CanonicalRow` | key `('meta_ads', 'Summer Sale', date(2026,6,1))` |
| 12 | `money.micros_to_usd` (API only) | `200.08` |

Line 2 is the clean path — no fallback, no normalization, no failure. The interesting branches in
the same file: line 9 (ISO date → step 9 returns `True`), line 12 (lowercased campaign →
`raw_campaign` populated), line 23 (`06/31/2026` → step 9 raises, row becomes a `ParseFailure`).
