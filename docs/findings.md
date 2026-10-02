# Data findings

What is wrong with the 15 provided delivery files, how I know, and what each defect does to the numbers.

Line numbers are 1-based with the CSV header as line 1. JSON positions are 0-based array indices. Every total
was computed twice by independent code paths (a `Decimal` pass and an integer/`awk` pass) that agree to the
last digit.

**Scope of the delivery set.** 3 platforms x 5 weeks = 15 expected slots. 15 files exist, but they do not map
one-to-one: LinkedIn is missing its 06-22 file and Google has an extra copy of 06-15. So there are 16 delivery
records — 15 files plus one empty slot.

---

## 1. Summary table

| # | File | Level | What's wrong | Evidence | Caught by | Effect on the numbers |
|---|---|---|---|---|---|---|
| R1 | `meta_ads_2026-06-01.csv` | row | Date `06/31/2026` does not exist — June has 30 days | line 23 | `values_parseable` | −1 row. Also leaves `App Install Push` with 6 of 7 days (§3) |
| R2 | `meta_ads_2026-06-15.csv` | row | `clicks` is an empty string | lines 11, 12, 17 | `required_fields_present` | −3 rows |
| R3 | `meta_ads_2026-06-22.csv` | row | Negative spend `-111.41` | line 8 | `metrics_non_negative` | −1 row, −$111.41, −25,217 impressions, −425 clicks |
| R4 | `linkedin_ads_2026-06-08.json` | row | The `clicks` key is absent from the object entirely | idx 3, 6, 13, 17, 20 | `required_fields_present` | −5 rows, −$416.44, −103,498 impressions. Also deletes 2026-06-14 from LinkedIn (§3) |
| N1 | `meta_ads_2026-06-01.csv` | row | Campaign name lowercased | lines 12, 20, 29 | `campaign_name_normalized` | 0 if normalized; would split 3 campaigns into 6 if not |
| N2 | `meta_ads_2026-06-01.csv` | row | Date in ISO `2026-06-01` while the rest of the file is `MM/DD/YYYY` | line 9 | `date_format_normalized` | 0 if normalized; −1 row if not |
| N3 | `meta_ads_2026-06-15.csv` | row | Trailing double space in campaign name | lines 13, 15, 30 | `campaign_name_normalized` | 0 if normalized; would split 2 campaigns if not |
| N4 | `google_ads_2026-06-01.csv` | file | 8 exact duplicate rows (43 raw rows, 35 distinct) | §2 | `duplicate_rows_within_file` | −8 rows, −$1,299.61, −445,773 impressions, −8,832 clicks. Double-counts them if not deduped |
| F1 | `meta_ads_2026-06-08.csv` | file | Spend reported in **cents**, not dollars | §4 | `spend_scale_vs_platform_baseline` | Quarantined: −35 rows, −1,403,288 impressions, −29,241 clicks. Ingested raw it would add **$480,070.00** instead of $4,800.70 |
| D1 | `linkedin_ads_2026-06-22.json` | delivery | Absent | only gap in the 3x5 grid | `delivery_present` | −21 rows (3 campaigns x 7 days). Magnitude estimate in §5 |
| D2 | `google_ads_2026-06-15_resend.csv` | delivery | Byte-identical to `google_ads_2026-06-15.csv`, and a non-standard file name | SHA-256 in §6 | `duplicate_delivery_content`, `file_name_matches_convention` | 0 as handled. Ingested it would double-count 35 rows, $6,442.69, 2,046,397 impressions, 42,861 clicks |

Plus six latent defects that produce no visible symptom on the development machine — §7. Those are the ones
most likely to make a reviewer's numbers differ from mine, so they are treated as first-class findings.

---

## 2. N4 — the duplicate rows in `google_ads_2026-06-01.csv`

43 data rows, 35 distinct. Eight rows appear exactly twice, with identical values in every column:

| Campaign | Day | Lines | Line gap |
|---|---|---|---|
| Search - Brand | 2026-06-07 | 2, 25 | 23 |
| Performance Max - All | 2026-06-01 | 4, 11 | 7 |
| YouTube Prospecting | 2026-06-03 | 6, 35 | 29 |
| YouTube Prospecting | 2026-06-07 | 8, 43 | 35 |
| Display Remarketing | 2026-06-01 | 10, 28 | 18 |
| Display Remarketing | 2026-06-07 | 14, 34 | 20 |
| Performance Max - All | 2026-06-04 | 19, 31 | 12 |
| YouTube Prospecting | 2026-06-06 | 32, 36 | 4 |

Two properties of this file shape the implementation:

1. **No duplicate pair is adjacent** — the smallest line gap is 4. Any neighbour-comparison or streaming
   dedupe finds zero of them. Full-row hashing across the whole file is required.
2. **This is the only one of the 15 deliveries whose rows are not grouped by campaign.** It has 35 campaign
   runs for 5 distinct campaigns (fully shuffled); every other delivery has exactly one contiguous,
   chronologically ordered run per campaign. The shuffle is itself a signal, and it is why all sample output
   in the quality report is explicitly sorted rather than relying on file read order.

After dedupe the file holds exactly 35 rows = 5 campaigns x 7 days, with no `(campaign, date)` key appearing
twice and no conflicting values anywhere.

---

## 3. Second-order effects of rejecting rows

Rejecting a row is not only a count change — it can remove a whole campaign-day or a whole calendar day. These
are more legible statements of the damage than row counts, so the pipeline reports them separately
(`campaign_day_coverage`).

**R1 almost certainly corrupted `01` into `31`.** The day-of-month set in `meta_ads_2026-06-01.csv` is
`{1,2,3,4,5,6,7,31}`, and the `App Install Push` block runs `31, 02, 03, 04, 05, 06, 07` while every other
campaign block in the file starts at `06/01`. The bad value sits exactly in the slot where `06/01` belongs.
That is strong support for reject-and-flag rather than any attempt to guess — but the report should say
*"App Install Push lost 2026-06-01"*, not merely *"one invalid date"*.

**R4 deletes an entire calendar day from LinkedIn.** Indices 6, 13 and 20 are all `2026-06-14` — one row for
each of the three LinkedIn campaigns — and all three are in the reject set. After ingestion LinkedIn has no
data at all for 2026-06-14.

Resulting campaign-day gaps:

| Delivery | Campaign-days lost |
|---|---|
| `meta_ads_2026-06-01.csv` | App Install Push: 06-01 |
| `meta_ads_2026-06-15.csv` | Brand Awareness Q2: 06-17, 06-18 · Retargeting - US: 06-16 |
| `meta_ads_2026-06-22.csv` | Summer Sale: 06-28 |
| `linkedin_ads_2026-06-08.json` | ABM Tier 1: 06-11, 06-14 · Thought Leadership: 06-14 · Talent Brand: 06-11, 06-14 |

Final June calendar coverage: **Google 30/30, Meta 30/30, LinkedIn 22/30** (missing 06-14, plus 06-22 through
06-28 from the absent delivery).

---

## 4. F1 — `meta_ads_2026-06-08.csv` reports spend in cents

**The factor is exactly 100.** The decisive evidence is that Meta's weekly accepted spend totals line up once
the file is divided:

```
meta_ads_2026-06-01.csv       4,452.87
meta_ads_2026-06-08.csv     480,070.00     / 100 = 4,800.70
meta_ads_2026-06-15.csv       4,392.38
meta_ads_2026-06-22.csv       4,338.20
meta_ads_2026-06-29.csv       1,589.69     (2-day week)
```

Supporting evidence:

| Measure | Meta's other 4 weeks | `meta_ads_2026-06-08.csv` |
|---|---|---|
| median spend per row | 123.53 – 139.51 | 13,263.00 |
| median CPC | $0.143 – $0.181 | $19.218 |
| median CPM | 3.09 – 3.91 | 355.04 |
| spend values that are whole dollars | 0 of 114 | **35 of 35** |
| impressions per day vs Meta median | — | 1.012x (normal) |
| clicks | — | normal |

Dividing by 100 puts the file's spend range at 38.81 – 270.76, against 36.46 – 278.35 across Meta's other
weeks, and it lands inside each individual campaign's own other-week range for all five campaigns.

**A note on how not to phrase this.** The ratio of the 06-08 median spend to the pooled other-weeks median is
104.08; median CPC gives 114.16 and median CPM gives 102.96. Those three numbers are mutually inconsistent
because each compares different row populations, so none of them measures the factor. The ratio is the
**detection signal**; the factor is exactly 100, and the weekly-total table above is why.

**Handling: quarantine the whole delivery** — 0 rows ingested, health FAIL, and the check records the inferred
factor plus the $4,800.70 the delivery would have contributed. The pipeline never rewrites reported money on
an inference.

The cost of that choice is real and is stated rather than hidden: quarantining also discards 1,403,288
impressions and 29,241 clicks for which there is no evidence of any problem. The alternative — divide spend by
100 and ingest — gives a June total of $53,509.72 instead of $48,709.02. Both numbers are published, and the
second is computed by the pipeline rather than by hand.

---

## 5. D1 — the missing LinkedIn delivery

`linkedin_ads_2026-06-22.json` does not exist. `delivery_present` reports the empty slot and its expected row
count: 3 campaigns x 7 days = **21 rows**.

For context in this document only, not as a check output: extrapolating from the mean of LinkedIn's three
complete 7-day weeks ($1,910.29, $1,983.33 and the partial 06-08 week), the gap is on the order of **$1,900 of
spend and 580,000 impressions**, roughly a quarter of LinkedIn's true month. That is an estimate from
neighbouring weeks, not a measurement, which is why the check reports only what it can know.

---

## 6. D2 — the duplicate Google delivery

```
4dd8a017b6e4694bb5b6cce87f3f19f9064fd9ad7c26b11c3b41cf353c8127d7  google_ads_2026-06-15.csv
4dd8a017b6e4694bb5b6cce87f3f19f9064fd9ad7c26b11c3b41cf353c8127d7  google_ads_2026-06-15_resend.csv
```

Byte-identical. `google_ads_2026-06-15.csv` matches the expected naming convention, so it is the original and
the resend is the superseded copy: 0 rows ingested, health WARN, with the relationship recorded both ways so
the health grid cell for that slot shows both files. The file name also trips
`file_name_matches_convention`, which is a separate warning from the duplicate-content one.

---

## 7. Latent defects — correct on this machine, wrong elsewhere

These produce no visible symptom in development. Each one silently changes a number that evaluation criterion
1 says the reviewers already know, so each is pinned by a test.

### L1 — Timezone: the highest-risk defect in the set

All 23 distinct LinkedIn `date_ts` values are exactly UTC midnight (`ts % 86_400_000 == 0`). That means
`datetime.fromtimestamp(ms / 1000)` — the obvious one-liner — reads them in the **host's** zone:

| TZ | dates shifted | leave June | change week |
|---|---|---|---|
| `UTC` | 0 / 23 | 0 | 0 |
| `Asia/Kolkata` (this machine, +0530) | 0 / 23 | 0 | 0 |
| `Europe/Berlin`, `Australia/Sydney` | 0 / 23 | 0 | 0 |
| `America/New_York` | **23 / 23** | 1 date | 4 dates |
| `America/Los_Angeles` | **23 / 23** | 1 date | 4 dates |

On any UTC-negative host every LinkedIn date moves back one day. `2026-06-01` becomes `2026-05-31`, outside
the reporting period entirely. The `date_within_delivery_week` rule then converts an off-by-one into **deleted
data**: 12 rows worth **$1,042.74** rejected, and all four LinkedIn deliveries flipped to FAIL.

Fix: `datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()`, never `utcfromtimestamp` (deprecated in
3.12). Pinned by a test that sets `TZ=America/New_York` — the one test a synthetic fixture on a UTC box
cannot replace.

### L2 — Rounding policy changes two published totals

**Google.** `google_ads_2026-06-15.csv` line 17 is `Display Remarketing,2026-06-16,64629999,USD,19615,680`.
`64629999` is the only cost value in all 193 Google rows that is not a multiple of 10,000 (the other
non-multiple is its twin in the resend file). It parks the Google total on exactly `$27,954.499999`:

```
exact                 27954.499999
ROUND_HALF_UP         27954.50      <- published
ROUND_DOWN / floor    27954.49
micros // 10000       27954.49
```

**LinkedIn.** The exact EUR-to-USD sum is `$5,869.9728`, and 63 of the 64 accepted rows produce a product with
3 or 4 decimal places:

```
round once at the aggregate    5869.97    <- published
round each row (HALF_UP)       5869.96
round each row (HALF_EVEN)     5869.96
truncate each row              5869.65
```

No row sits on an exact half-cent, so the rounding **mode** is irrelevant — the drift is pure accumulation
across 63 rows and cannot be fixed by choosing a different mode. Only rounding once can.

Consequence for the schema: spend is stored as integer **micro-USD** and quantized to cents exactly once, at
the API boundary, with `ROUND_HALF_UP`. A `NUMERIC(12,2)` spend column or a `round(x, 2)` in the normalizer
would force per-row rounding and silently publish `$48,709.01` instead of `$48,709.02`. Micro-USD is lossless
for every row here: EUR amounts have 2 decimals and the rate has 2, so USD has at most 4.

### L3 — `Decimal(1.08)` is not 1.08

`json.load` returns the rate as a float, and:

```
Decimal(1.08)       = 1.0800000000000000710542735760100185871124267578125
Decimal(str(1.08))  = 1.08
```

Rates are built with `Decimal(str(value))`. Separately, `exchange_rates.json` has top-level keys
`['comment', 'rates']`, so the map must be read as `j["rates"]` — iterating the top level would treat
`comment` as a currency with a string rate.

### L4 — `Decimal('')` is not a `ValueError`

```
Decimal('')     -> decimal.InvalidOperation   (subclasses ArithmeticError, NOT ValueError)
Decimal('abc')  -> decimal.InvalidOperation
Decimal(None)   -> TypeError
int('')         -> ValueError
```

A row parser written `except ValueError` catches the empty `clicks` field but lets an empty **spend** field
escape into the generic check wrapper, where it becomes `status="error"` instead of a correctly classified
rejection. Row parsing catches `(ValueError, ArithmeticError, TypeError)`.

### L5 — Discovery must skip dotfiles

`data/.DS_Store` exists (10,244 bytes, a sibling of `deliveries/`), and there is a second one at the repo
root. `glob` skips dotfiles but `os.listdir`, `os.walk`, `Path.iterdir` and `Path.rglob('*')` all return them,
and opening one raises `UnicodeDecodeError` at byte 3131. Without an explicit rule the delivery count would be
16 on this machine and 15 on a reviewer's Linux box, so this document would stop matching the program's
output. Discovery is scoped to `data/deliveries/*.csv` and `*.json` with dotfiles skipped explicitly.

### L6 — Never split a CSV line by hand

With `newline=''` and a manual `split(',')`, the last field of a CRLF row carries a stray `\r`. On
`meta_ads_2026-06-15.csv` line 11 the `clicks` field becomes `'\r'`, so `field == ''` and `not field` are both
False, and the three R2 rows get misclassified as generic parse failures instead of "clicks missing" — the
quality report would then mis-describe a defect it did catch. `cut -d, -f5` and `awk -F,` have the same
problem on the last column, so ad-hoc shell QA of these files is unreliable. Python's `csv` module is clean
either way; all parsing goes through it.

---

## 8. The degenerate result set

The brief names one API edge case: *CPC when clicks = 0*. **It is unreachable from the real data.** Across all
accepted rows the minimum clicks value is **99** and the minimum impressions value is **7,221**; no row has a
zero in either column, and no campaign group on any filter can produce a zero denominator from real values.

The only live-reachable zero denominator is an **empty result set** — and the quality policy manufactures
those on exactly the filters a reviewer reaches for after drilling into the red cells in the health grid:

| Filter | rows | spend | CTR | CPC |
|---|---|---|---|---|
| `platform=meta_ads`, `2026-06-08` to `06-14` (quarantined) | **0** | 0.00 | null | null |
| `platform=linkedin_ads`, `2026-06-22` to `06-28` (missing delivery) | **0** | 0.00 | null | null |
| `platform=linkedin_ads`, `date=2026-06-14` (all rows rejected) | **0** | 0.00 | null | null |
| all platforms, `2026-06-08` to `06-14` | 51 | 7,542.17 | 0.0211 | 0.1557 |

So the empty state is the only place the named edge case can actually be demonstrated. It returns zeroed
totals with null CTR and CPC — never a 404 and never an error — and the UI says *why* the set is empty, naming
the quarantined or missing delivery and linking to the health view. Without that, the cells the health grid
exists to highlight lead to a blank table indistinguishable from a broken frontend.

---

## 9. Calibration: why there are no row-level statistical checks

Natural day-to-day variance within a single campaign is large enough that a row-level median-ratio check is
noise. False positives against each campaign's own median:

| tolerance | impressions | clicks | spend | CTR | CPC |
|---|---|---|---|---|---|
| +/-30% | 162 | 225 | 104 | 203 | 205 |
| +/-50% | 85 | 163 | 26 | 121 | 148 |
| +/-100% | 13 | 64 | 0 | 31 | 44 |
| +/-150% | 3 | 16 | 0 | 6 | 14 |
| +/-200% | 0 | 7 | 0 | 0 | 3 |
| +/-300% | 0 | 1 | 0 | 0 | 0 |

Global ranges: CTR 0.00804 – 0.03494 (4.3x), CPC $0.070 – $0.597 (8.5x), clicks 99 – 4,191. A row-level
statistical check would have to be looser than 3x to be clean, at which point it catches the 100x cents
defect and literally nothing else.

**Therefore: row-level checks are plausibility bounds only** (real calendar date, spend >= 0,
clicks <= impressions, date inside the delivery week, currency known). Statistics belong at file and delivery
aggregate level, where the signal survives.

Two aggregate bands, both measured:

- **Spend scale** (`spend_scale_vs_platform_baseline`): median CPM against the platform's other deliveries;
  quarantine outside `[1/10, 10]`. The defective file is ~103x; every clean file is within 1.2x of its
  platform baseline. Roughly 10x of margin on both sides.
- **Row volume** (`row_volume_vs_platform_baseline`): accepted rows per **covered day**; WARN outside
  `[0.5, 2.0]`. Observed range on accepted rows is 0.762 – 1.029, the minimum being
  `linkedin_ads_2026-06-08.json` after its 5 rejections, so the band has about 1.5x of margin.

Day-normalization is not optional. The 06-29 week legitimately covers 2 days, and a raw week-over-week volume
comparison would report all three of its deliveries as a collapse — Google −71.8%, Meta −63.4%, LinkedIn
−70.3% — on completely clean data.

---

## 10. Reference totals, and the audit trail from raw to final

### Raw parsed, per file — what the adapters produce before any check runs

A row is *parsed* if the adapter can build a canonical row from it. The 9 parse failures are the rows whose
date or integer fields cannot be read at all; every other defect is a check decision, not a parse failure.

| Delivery | parsed | failed | spend USD | impressions | clicks |
|---|---|---|---|---|---|
| `google_ads_2026-06-01.csv` | 43 | 0 | 8,188.91 | 2,535,740 | 53,362 |
| `google_ads_2026-06-08.csv` | 35 | 0 | 6,154.21 | 1,894,078 | 39,951 |
| `google_ads_2026-06-15.csv` | 35 | 0 | 6,442.69 | 2,046,397 | 42,861 |
| `google_ads_2026-06-15_resend.csv` | 35 | 0 | 6,442.69 | 2,046,397 | 42,861 |
| `google_ads_2026-06-22.csv` | 35 | 0 | 6,605.91 | 1,961,608 | 44,873 |
| `google_ads_2026-06-29.csv` | 10 | 0 | 1,862.39 | 569,081 | 15,130 |
| `linkedin_ads_2026-06-01.json` | 21 | 0 | 1,910.29 | 629,691 | 14,504 |
| `linkedin_ads_2026-06-08.json` | 16 | 5 | 1,387.96 | 401,076 | 8,485 |
| `linkedin_ads_2026-06-15.json` | 21 | 0 | 1,983.33 | 605,299 | 12,102 |
| `linkedin_ads_2026-06-29.json` | 6 | 0 | 588.38 | 162,156 | 2,934 |
| `meta_ads_2026-06-01.csv` | 34 | 1 | 4,452.87 | 1,179,119 | 26,172 |
| `meta_ads_2026-06-08.csv` | 35 | 0 | 480,070.00 | 1,403,288 | 29,241 |
| `meta_ads_2026-06-15.csv` | 32 | 3 | 4,392.38 | 1,376,283 | 25,915 |
| `meta_ads_2026-06-22.csv` | 35 | 0 | 4,338.20 | 1,411,763 | 30,646 |
| `meta_ads_2026-06-29.csv` | 10 | 0 | 1,589.69 | 448,117 | 9,644 |
| **Total** | **403** | **9** | **536,409.91** | **18,670,093** | **398,681** |

### What the checks then remove

| Step | Rows | Spend removed |
|---|---|---|
| raw parsed | 403 | — |
| `duplicate_rows_within_file` on `google_ads_2026-06-01.csv` | −8 | $1,299.61 |
| `duplicate_delivery_content` — the resend delivery | −35 | $6,442.69 |
| `metrics_non_negative` — `meta_ads_2026-06-22.csv` line 8 | −1 | −$111.41 (a negative, so the total rises) |
| `spend_scale_vs_platform_baseline` — quarantine `meta_ads_2026-06-08.csv` | −35 | $480,070.00 |
| **final** | **324** | — |

### Final

| | rows | spend USD | impressions | clicks | CTR | CPC |
|---|---|---|---|---|---|---|
| Google Ads | 150 | 27,954.50 | 8,561,131 | 187,345 | 0.0219 | 0.1492 |
| LinkedIn Ads | 64 | 5,869.97 | 1,798,222 | 38,025 | 0.0211 | 0.1544 |
| Meta Ads | 110 | 14,884.55 | 4,390,065 | 91,952 | 0.0209 | 0.1619 |
| **Total** | **324** | **48,709.02** | **14,749,418** | **317,322** | **0.0215** | **0.1535** |

Exact unrounded total: `48,709.022799`. Google's exact micro total: `27,954,499,999` micros.

Google reconciles exactly: `35,696.80 − 6,442.69 (resend) − 1,299.61 (8 duplicate rows) = 27,954.50`.

Alternative under the scale-correction policy for F1: 359 rows, $53,509.72, 16,152,706 impressions,
346,563 clicks, CTR 0.0215, CPC $0.1544.

---

## 11. Dimensions checked and found clean

Recorded so that the checks which never fire are visibly deliberate guards rather than oversights.

**File hygiene.** No BOM in any of the 16 files. No lone CR. No tab characters. No quoted fields and no
embedded commas anywhere, so there is no CSV-quoting hazard. Zero bytes above 127 in any file. All 10 CSVs are
CRLF-terminated including the final line; all 5 JSON files are LF-only with no trailing newline.

**Values.** Impressions and clicks are integer-typed in all 412 raw rows, with no zeros, no strings and no
floats. All 150 Meta spend values match `-?\d+\.\d{2}`. Google's `Currency` is `USD` in 193 of 193 rows and
`Day` is ISO in 193 of 193. No row anywhere has `clicks > impressions`.

**Campaign names.** Nothing beyond the 6 rows in N1 and N3. 18 distinct raw strings collapse to 13 canonical
campaigns, all pure ASCII and already NFC-normalized. No leading or trailing whitespace in any non-campaign
field in any CSV. Note that N1 and N3 are one problem, not two: `brand awareness q2` has three raw spellings
across two files — `Brand Awareness Q2` (x27), `brand awareness q2` (x1), `Brand Awareness Q2  ` (x2) — so
case-folding alone or trimming alone still leaves that campaign split in the metrics view. Both must be
applied before grouping.

**Currencies.** Used in the data: `{USD, EUR}`. Declared in the rates file: `{USD, EUR}`. Nothing
used-but-missing, nothing declared-but-unused.

**Calendar and cadence.** Every week start is a Monday, and the final week is legitimately 2 days (2026-06-29
and 06-30), matching the brief. Under the correct UTC reading, zero rows across all 15 deliveries fall in a
different Monday-start week than their file name implies. Every campaign appears in every week its platform
delivered: Google 5x5, Meta 5x5, LinkedIn 3x4. No campaign starts or stops mid-month.

**Keys.** Zero within-file `(campaign, date)` conflicts with differing values, and zero post-normalization
`(platform, campaign, date)` collisions across the entire corpus.

**Delivery matrix.** 14 of 15 expected slots filled, exactly one empty (LinkedIn 06-22) and exactly one
doubled (Google 06-15). No unrecognized platform file. No case of two *different* files competing for one
slot. No unparseable or empty file. No missing or extra column.

The nine checks that therefore never fire on this data, and exist as general correctness guards:
`clicks_not_above_impressions`, `date_within_delivery_week`, `currency_in_rates_file`,
`file_structure_valid`, `duplicate_keys_within_file`, `row_volume_vs_platform_baseline`,
`single_file_per_slot`, `platform_recognized`, `canonical_key_unique_across_deliveries`.

One honest caveat on `currency_in_rates_file`: Meta's CSVs carry **no currency column at all** — USD is
implied solely by the header name `spend_usd`. So that check structurally cannot cover 1 of the 3 platforms,
and USD-for-Meta is a documented assumption, not a passed check.

---

## 12. How these findings were produced

Everything above comes from reading the 16 files directly with Python standard library tooling — `csv`,
`json`, `decimal`, `hashlib`, `datetime` — plus `shasum`, `grep` and `awk` for independent cross-checks. No
value was taken on trust from a single code path: the reference totals were computed by a `Decimal`
implementation and an integer-arithmetic implementation written separately, and every line number was
confirmed with `grep -n`. The timezone, rounding and exception-type findings in §7 were each reproduced by
running the alternative implementations side by side and recording both outputs.
