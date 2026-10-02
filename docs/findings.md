# Data findings

What is wrong with the 15 provided delivery files. Line numbers are 1-based with the CSV header
as line 1; JSON positions are array indices. Totals were computed twice by independent code paths
that agree exactly.

## Delivery map

3 platforms x 5 weeks = 15 expected slots. 15 files exist but do not map one-to-one: LinkedIn is
missing 06-22, Google has a duplicate of 06-15. So **16 delivery records**.

## Defects

| # | File | Level | What's wrong | Where | Effect |
|---|---|---|---|---|---|
| R1 | `meta_ads_2026-06-01.csv` | row | `06/31/2026` — June has 30 days | line 23 | −1 row |
| R2 | `meta_ads_2026-06-15.csv` | row | `clicks` is empty | lines 11, 12, 17 | −3 rows |
| R3 | `meta_ads_2026-06-22.csv` | row | spend is `-111.41` | line 8 | −1 row |
| R4 | `linkedin_ads_2026-06-08.json` | row | `clicks` key absent | idx 3, 6, 13, 17, 20 | −5 rows, −$416.44 |
| N1 | `meta_ads_2026-06-01.csv` | row | campaign lowercased | lines 12, 20, 29 | 0 once normalized |
| N2 | `meta_ads_2026-06-01.csv` | row | ISO date in an `MM/DD/YYYY` file | line 9 | 0 once normalized |
| N3 | `meta_ads_2026-06-15.csv` | row | trailing spaces in campaign | lines 13, 15, 30 | 0 once normalized |
| N4 | `google_ads_2026-06-01.csv` | file | 8 exact duplicate rows (43 raw, 35 distinct) | — | −8 rows, −$1,299.61 |
| F1 | `meta_ads_2026-06-08.csv` | file | spend in **cents**, factor exactly 100 | all 35 rows | quarantined: −35 rows |
| D1 | `linkedin_ads_2026-06-22.json` | delivery | absent | — | −21 rows |
| D2 | `google_ads_2026-06-15_resend.csv` | delivery | byte-identical copy, non-standard name | — | 0; would double-count $6,442.69 |

**N1 and N3 are one problem.** `brand awareness q2` has three spellings across two files, so
trimming alone or case-folding alone still splits it in the metrics view. Both are needed.

**N4 needs full-file hashing.** No duplicate pair is adjacent (smallest line gap is 4), so
neighbour comparison finds none of them.

**R4 deletes a whole day.** Indices 6, 13 and 20 are all 2026-06-14, one per campaign, so LinkedIn
has no data at all for that date. Final coverage: Google 30/30, Meta 30/30, LinkedIn 22/30.

## F1: the cents file

Meta's weekly accepted spend lines up once divided by 100:

```
06-01    4,452.87
06-08  480,070.00   / 100 = 4,800.70
06-15    4,392.38
06-22    4,338.20
06-29    1,589.69   (2-day week)
```

All 35 spend values are whole dollars, against 0 of 114 in Meta's other weeks. Median CPM is 355
against 3.09–3.91. Impressions and clicks are normal, so only the spend column is wrong.

Handling: **quarantine** — 0 rows, FAIL, and report the factor plus the $4,800.70 it would have
contributed. Never rewrite reported money on an inference. The cost is stated, not hidden: it also
discards 1,403,288 impressions and 29,241 clicks that are fine. The alternative (divide by 100 and
ingest) would give $53,509.72 instead of $48,709.02.

Say "spend in cents, divide by exactly 100", not "~104x". The median-spend ratio gives 104.08, CPC
gives 114.16, CPM gives 102.96, because each compares different row populations. The ratio is the
detection signal; 100 is the factor.

## Environment gotchas

Five things that are correct on this machine and wrong elsewhere. Each is pinned by a test.

1. **Timezone.** All 23 LinkedIn timestamps are exactly UTC midnight, so `fromtimestamp(ms/1000)`
   without `tz` reads the host zone. On `America/New_York` every date moves back a day,
   `2026-06-01` leaves the period, and the date-in-week rule then rejects 12 rows worth $1,042.74.
   Use `tz=timezone.utc`.
2. **Rounding.** `google_ads_2026-06-15.csv` line 17 is `64629999` micros — the only non-multiple
   of 10,000 in 193 rows — putting the Google total on exactly $27,954.499999. Half-up gives .50;
   truncating or `micros // 10000` gives .49. LinkedIn's exact sum is $5,869.9728: rounding once
   gives .97, rounding per row gives .96 under *any* mode. So: integer micro-USD, rounded once at
   the API boundary.
3. **`Decimal(1.08)`** is `1.080000000000000071...` because `json` returns a float. Use
   `Decimal(str(rate))`, and read `document["rates"]` — the file has a `comment` key too.
4. **`Decimal('')`** raises `InvalidOperation`, an `ArithmeticError`, not a `ValueError`
   (`int('')` is a `ValueError`). Catch `(ValueError, ArithmeticError, TypeError)`.
5. **`data/.DS_Store`** exists. `glob` skips dotfiles but `iterdir` and `walk` do not, so the
   delivery count would be 16 on a Mac and 15 on Linux. Skip dotfiles explicitly.

## Normalization per platform

| | Meta | Google | LinkedIn |
|---|---|---|---|
| format | CSV, CRLF | CSV, CRLF | JSON array |
| date | `%m/%d/%Y`, then `%Y-%m-%d` | `%Y-%m-%d` | epoch ms, UTC |
| spend | `spend_usd`, USD | `Cost (micros)` ÷ 1e6 | `spend.amount` in `spend.currency` |
| currency | **no column** — USD assumed from the header name | explicit, all USD | all EUR, × 1.08 |

**Date format is proved, not assumed.** 91 Meta rows have a second component above 12, impossible
as a month. A wrong declaration is also self-exposing: under `DD/MM`, `06/02/2026` reads as
6 February, falls outside the week, and the date-in-week check lights up every row.

**FX direction is read from the file:** *"1 unit of currency = N USD"* → multiply. Magnitudes do
not disambiguate (×1.08 and ÷1.08 are both plausible against the other platforms), so the file's
own comment is the only evidence.

**Campaign identity** is `(platform, campaign)`: trim, group case-insensitively, display the most
common spelling, ties broken by count then spelling so the key is deterministic. Never `.title()`
— it would give `Retargeting - Us`.

## Reference totals

| | rows | spend USD | impressions | clicks | CTR | CPC |
|---|---|---|---|---|---|---|
| Google | 150 | 27,954.50 | 8,561,131 | 187,345 | 0.0219 | 0.1492 |
| LinkedIn | 64 | 5,869.97 | 1,798,222 | 38,025 | 0.0211 | 0.1544 |
| Meta | 110 | 14,884.55 | 4,390,065 | 91,952 | 0.0209 | 0.1619 |
| **Total** | **324** | **48,709.02** | **14,749,418** | **317,322** | **0.0215** | **0.1535** |

From raw to final: 403 rows parse, then −8 duplicates, −35 resend, −1 negative spend,
−35 quarantined = 324. Google reconciles exactly:
`35,696.80 − 6,442.69 − 1,299.61 = 27,954.50`.

## Checked and clean

No BOM, no non-ASCII, no quoted fields or embedded commas. Impressions and clicks are integers
everywhere, with no zeros. Both data currencies are in the rates file. Every week starts on a
Monday and the last is legitimately 2 days. No row falls in a different week than its filename
implies. Every campaign appears in every week its platform delivered. Zero `(campaign, date)`
conflicts and zero cross-delivery key collisions.

One consequence worth stating: **no real row has zero clicks** (minimum 99), so the brief's
CPC-when-clicks-is-0 case is only reachable through an empty filter result — which the quarantine
and the missing delivery both produce.
