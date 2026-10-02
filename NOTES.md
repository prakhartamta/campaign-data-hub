# Deferred work

Decisions to leave something out, with the reason. Feeds the README's "what I'd do with more time".

## Checks not built

Five checks were designed and dropped. None fires on the provided data, and none is needed for
correctness, so building them would have been coverage for its own sake.

- `duplicate_keys_within_file` — the same (campaign, date) twice with *different* values inside one
  file. Zero occurrences in the data.
- `row_volume_vs_platform_baseline` — accepted rows per covered day against the platform's other
  deliveries. Would catch a truncated upload. The observed range is 0.762-1.029, so there is
  nothing to find here.
- `single_file_per_slot` as a separate check — folded into the duplicate-delivery resolution, which
  already has to decide which of two files wins.
- `platform_recognized` as a separate check — discovery already reports an unplaceable file and the
  pipeline fails it, so a check would only restate that.
- Cross-delivery key uniqueness as a separate check — the in-memory key collapse already asserts
  it, which is the behaviour that matters. A check would be the reporting half.

## Known gaps

- **Ragged CSV rows.** A money field containing an unquoted thousands separator shifts the columns,
  so the row is reported as "impressions is not an integer" rather than as a column-count mismatch.
  `csv.DictReader` exposes the overflow under a `None` key, which `file_structure_valid` should
  read. Correct verdict, misleading reason.
- **No lateness signal.** A delivery that arrives a week late simply flips its slot from missing to
  present on the next recompute. Nothing records that it was late; file mtime is the only available
  signal and it does not survive a copy.
- **Subdirectory scanning.** Discovery reads one flat directory. Going recursive would need the
  dotfile guard to check every path component, and `delivery_id` would have to become a relative
  path rather than a file name, since two folders could hold the same name.

## If there were more time

- **Spend-column quarantine instead of whole-file.** The defective Meta delivery has one bad
  column; quarantining the file also discards 1,403,288 impressions and 29,241 clicks that are
  demonstrably fine. Ingesting the rows with spend marked unusable would preserve them, at the cost
  of a nullable money column and a more complicated aggregation. The current choice is the
  conservative one and both totals are published.
- **A per-delivery re-ingest.** The pipeline is a full recompute, which is what makes idempotency
  provable at the database level. Re-ingesting one delivery would be faster but needs the
  cross-delivery checks to be incremental.
- **A database-backed ingestion lock.** The current lock is per-process, so the 409 response only
  holds within one worker. SQLite's single-writer transaction already makes a concurrent run safe,
  so this is a UX guard rather than a correctness one, but it is why uvicorn is pinned to one
  worker.
- **Alerting on health.** The system makes a broken delivery visible; it does not tell anyone. A
  WARN or FAIL on a delivery is exactly the event someone would want pushed.
