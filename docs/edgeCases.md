# Edge cases

Revision sheet: the question, the shortest true answer, and where it lives. Evidence is in
[findings.md](findings.md).

**Status:** `done` = code exists and I ran it · `planned` = decided, module not written yet ·
`guard` = implemented, never fires on this data, deliberate.

Implemented so far: `config.py`, `money.py`, `adapters/base.py`, `discovery.py`.

## Dates

| Question | Answer | Status |
|---|---|---|
| `03/04/2026` — March 4 or April 3? | Each adapter declares ordered formats, primary first. No inference. Unmatched → rejected, naming the value and formats tried. | done (`parse_date`) |
| How do you know Meta is MM/DD? | 91 rows have a second component above 12, impossible as a month. And a wrong guess is self-exposing: under DD/MM, `06/02/2026` reads as 6 February, falls outside the week, and every row fails the date-in-week check. | done |
| `06/31/2026`? | June has 30 days, `strptime` rejects it under every format → `ParseFailure`. Knock-on: `App Install Push` then has 6 of 7 days. The file's day set is `{1..7, 31}` and that campaign starts at 31, so `01` was corrupted into `31`. Still reject, never guess. | done |
| Naive epoch conversion | All 23 LinkedIn timestamps are UTC midnight, so `fromtimestamp(ms/1000)` reads the host zone. On US zones every date shifts back a day and the date-in-week rule then deletes 12 rows. Use `tz=timezone.utc`. | planned |
| LinkedIn sends seconds not ms | Nothing raises. `1780272000/1000` is 1970-01-21, a valid date. `parse_date` never sees it — it is an int, not text. Caught one stage later by `date_within_delivery_week`, 100% rejected. | planned |
| The last week is 2 days | `expected_weeks` truncates at `PERIOD_END`; `days_covered` returns 2. Raw row counts would read as a 71% collapse, so every volume comparison divides by days covered. | done |
| A delivery arrives late | The grid is regenerated from config every run, not persisted, so the next recompute flips the slot from MISSING to present. Nothing records lateness; mtime is the only signal and it is unreliable. | done |

## Money

| Question | Answer | Status |
|---|---|---|
| Why micro-USD, not a decimal column? | One Google row (`64629999` micros) puts the total on exactly $27,954.499999 — half-up gives .50, truncating gives .49. And 63 of 64 LinkedIn rows convert to a non-whole number of cents, so rounding per row loses a cent under *any* mode. Round once, at the API boundary. | done |
| Which way does the rate go? | The file says *"1 unit of currency = N USD"* → multiply. Magnitudes do not disambiguate. | done |
| `Decimal(1.08)` | `1.080000000000000071...`, because `json` returns a float. Use `Decimal(str(rate))`. | done |
| Rates file shape | Top-level keys are `comment` and `rates`. Read `document["rates"]`. | done |
| A currency needing 7 decimals | `to_micros_usd` raises rather than truncating. | done |
| Spend in the wrong unit | `meta_ads_2026-06-08.csv`: factor exactly **100**. Quarantine, 0 rows, FAIL, report the factor and the $4,800.70 it would have added. Never rewrite money on an inference. | planned (check) |
| Why CPM for the scale check? | Spend changes legitimately with volume and week length; CPM is a rate, so it is flat. Clean files sit within 1.2x of baseline, the defect is 103x. A threshold of 10 sits in the empty gap — move it to 3 or 50 and nothing changes. | planned (check) |

## Parsing

| Question | Answer | Status |
|---|---|---|
| CRLF files | With `newline=''` and a manual `split(',')` the last field keeps a stray `\r`, so an empty `clicks` becomes `'\r'` and the emptiness test misses it. The `csv` module is clean; always use it. | planned (rule) |
| `"1,200.50"` in a money field | Quoted → `Decimal` raises `InvalidOperation`. Unquoted → the columns shift, spend becomes `1`, and the row dies on `int('200.50')` instead. The overflow lands under `csv`'s `None` key, so `file_structure_valid` should report a ragged row rather than "impressions is not an integer". | planned |
| `Decimal('')` | Raises `InvalidOperation`, an `ArithmeticError`, **not** a `ValueError`. `int('')` *is* a `ValueError`, `Decimal(None)` is a `TypeError`. Catch all three or an empty spend escapes as a crash. | planned (rule) |
| A missing column | Adapter returns `missing_fields`; the delivery is quarantined, 0 rows, FAIL. | planned (guard) |
| Meta's currency | There is **no column**. USD is implied by the header name `spend_usd`, so `currency_in_rates_file` structurally cannot cover one of three platforms. Documented as an assumption, not a passed check. | planned |
| `.DS_Store` | Exists in `data/`. `glob` skips dotfiles but `iterdir` does not, so the count would be 16 on a Mac and 15 on Linux. Skipped explicitly. | done |

## Identity and keys

| Question | Answer | Status |
|---|---|---|
| One campaign, three spellings | `brand awareness q2` appears as `Brand Awareness Q2` (x27), lowercased (x1) and with trailing spaces (x2), across two files. Trimming alone or case-folding alone still splits it. Both, then vote on the most common spelling, ties by count then spelling. Never `.title()`. | planned (step 5) |
| Why is campaign identity per-platform? | Drop `platform` from the key and Meta's `Summer Sale` collides with Google's on the same date. The metrics PK rejects the second row, and since the recompute is one transaction, the whole run rolls back. | done (`CanonicalRow.key`) |
| 8 duplicate rows in one file | No pair is adjacent — smallest line gap is 4 — so neighbour comparison finds none. Full-file hashing required. It is also the only file whose rows are not grouped by campaign, which is why samples are explicitly sorted. | planned (check) |
| Why collapse keys in memory? | The check actions are reject/quarantine/flag, none of which removes a row. "Keep one duplicate" needed a fourth action, `drop`, plus a dict keyed by `(platform, campaign, date)` built **before** the INSERT with an assert after it. | planned (step 6) |

## Deliveries and slots

| Question | Answer | Status |
|---|---|---|
| Two files in one slot: duplicate or conflict? | Same names, opposite verdicts. Byte-identical → count once, copy gets 0 rows and WARN. Different → two files disagree about one week, so FAIL; never pick silently. Discovery cannot tell: it reads names only, no `hashlib`. The missing information is the content hash, available in step 2 and compared in step 3. | done (detection), planned (resolution) |
| Which file is the original? | The one matching the naming convention; otherwise first by sorted name, so the choice is deterministic rather than filesystem-order dependent. | planned |
| A delivery never arrived | The grid comes from config, not the directory, so the slot exists with zero files and FAILs with its expected name. | done |
| Junk appended to a name | `_resend`, ` (1)`, `-copy`, `.final` all resolve correctly. The date is read off the front by fixed width, not by splitting on a separator, because the separator is unpredictable. | done |
| Unknown platform | `tiktok_ads_...csv` → unplaced, FAIL, never crashes the run. | done (guard) |
| Known platform, unreadable week | `meta_ads_june.csv` → unplaced. Without a week there is no window to validate dates against. | done (guard) |
| `meta` vs `meta_ads` | Longest prefix first, or `meta_ads_2026-06-01.csv` would resolve to `meta` with a week of `ads_2026-06-01`. | done |
| Cadence becomes twice a week | Two shorter windows → change `WEEK_DAYS`, nothing in discovery changes (verified at 3). Two files per window → `expected_filename` collides, needs a part number in the convention. | done |

## Health

| Question | Answer | Status |
|---|---|---|
| Why is the reject rate split from suppression? | Google 06-01 is 8 dropped duplicates of 43 = 18.6% > 10% → FAIL, although it is a perfect 35 rows after dedupe. And the resend is 0-of-35 = 100% → FAIL, although the policy promises WARN. So `rows_rejected` counts validity failures only; `rows_suppressed` counts dedupe, duplicate file and quarantine. | planned |
| Why ordered rules, not an OR? | The two cases above resolve differently depending on which condition is tested first. Ordering makes it decidable. | planned |
| A check crashes | `status="error"` is neither pass nor fail, so it left the delivery PASS with a hidden red check — the brief's opening failure, via the mechanism meant to prevent it. An errored check inherits its declared severity. | planned |
| Why no row-level statistical checks? | Measured: per-campaign CPC spans 8.5x and CTR 4.3x, so a row-level ratio check must be looser than 3x to be clean, at which point it catches only the 100x defect. Row checks are plausibility bounds; statistics are aggregate-level. | planned |

## API and UI

| Question | Answer | Status |
|---|---|---|
| CPC when clicks = 0 | Unreachable from real rows — the minimum is 99 clicks. The only live path is an **empty filter result**, which the quarantine and the missing delivery both produce. So the empty state is the demo of this case. | done (primitives) |
| What does an empty result return? | Zeroed totals with null CTR and CPC. Never a 404, never an error. The UI names the quarantined or missing delivery, or the two red cells lead to a blank table that looks broken. | planned |
| Two runs differ, all numbers correct | DELETE + INSERT reuses freed pages, so physical row order changes. Without explicit `ORDER BY`, paging can repeat rows and the live diff fails on ordering alone. | planned |
| Why `raw_spend_unit`? | Google's raw spend is micros, Meta's dollars, LinkedIn's EUR. One column without a unit renders `$117,410,000` beside `$117.41`. | done (model) |
| FastAPI's own errors | A bad `limit` is rejected by Pydantic before the handler, returning `{"detail": [...]}`, not the envelope. Needs handlers for `RequestValidationError`, `StarletteHTTPException` and a catch-all. | planned |
| Why `def`, not `async def`? | A synchronous pipeline in an async handler blocks the event loop for the whole run, so the healthcheck stalls and the 409 branch cannot be demonstrated. | planned |
| The slot with two files | The grid is one cell per slot but health is per delivery, so that cell had no defined colour. `slot_health = worst(deliveries)`. Routing by `(platform, weekStart)` also avoids a `.json` in a SPA URL. | planned |
| Concurrent runs | 409 via an in-process lock. Worth saying: SQLite's single-writer transaction already makes it *safe*, so the 409 is UX, not correctness. Hence `--workers 1`, documented. | planned |

## Where would you change…

| Change | Where |
|---|---|
| New platform | New `app/adapters/<name>.py` + register it. Two files. |
| New platform with `.tsv` | The above, plus `.tsv` in `DELIVERY_EXTENSIONS`, and pass `delimiter="\t"` to `DictReader`. |
| New check | One class in `app/checks/`, registered. Nothing else. |
| A threshold | One constant in `config.py`. |
| FX direction | `money.py` `to_micros_usd` — and the stored `fx_rate` lineage changes meaning with it. |
| Cadence | `WEEK_DAYS` in `config.py`. |
| A platform's date format | That adapter's `DATE_FORMATS` tuple, primary first. |
| Campaign identity rule | `CanonicalRow.key`, the `metrics` PK and the summary grouping, together. |
| Reporting period | `PERIOD_START` / `PERIOD_END`. The grid and the short last week follow. |

## The trace

`meta_ads_2026-06-01.csv` line 2 — `Summer Sale,06/01/2026,200.08,37215,574`:

`discover` → `expected_weeks` (5 windows) → `build_slots` (15 slots) → `list_candidate_files`
(15 paths, no `.DS_Store`) → `parse_delivery_name` → `('meta_ads', 2026-06-01, False)` →
`load_rates` → `{'USD': 1.0, 'EUR': 1.08}` as `Decimal` → `csv.DictReader` → `parse_date` →
`(date(2026,6,1), False)` → `to_micros_usd` → `200080000` → `CanonicalRow` with key
`('meta_ads', 'Summer Sale', 2026-06-01)` → `micros_to_usd` at the API → `200.08`.

Line 2 is the clean path. The branches in the same file: line 9 is ISO (normalization flag), line
12 is lowercased (`raw_campaign` populated), line 23 is `06/31/2026` (becomes a `ParseFailure`).
