"""Ingestion CLI: python -m app.ingest

Prints per-delivery and per-platform totals. Output is deterministic, so running it twice and
diffing the two is a real idempotency check rather than a claim.
"""

from __future__ import annotations

import sys

from .db import create_all, create_db_engine, create_session_factory
from .money import micros_to_usd
from .pipeline import run_pipeline


def format_delivery_table(result) -> list[str]:
    """Render one line per delivery, ordered by delivery id."""
    lines = [
        "%-34s %-13s %6s %7s %8s %11s %7s %13s"
        % ("delivery", "platform", "rows", "failed", "suppr.", "spend_usd", "status", "note")
    ]
    for outcome in result.outcomes:
        note = ""
        if outcome.is_missing:
            note = "missing"
        elif outcome.duplicate_of:
            note = "duplicate of " + outcome.duplicate_of
        elif outcome.structural_error:
            note = outcome.structural_error[:40]
        elif outcome.has_name_suffix:
            note = "non-standard name"
        lines.append(
            "%-34s %-13s %6d %7d %8d %11s %7s %13s"
            % (
                outcome.delivery_id,
                outcome.platform or "-",
                len(outcome.rows),
                len(outcome.failures),
                outcome.rows_suppressed,
                micros_to_usd(outcome.spend_usd_micros),
                outcome.health,
                note,
            )
        )
    return lines


def format_platform_table(result) -> list[str]:
    """Render one line per platform, plus a total."""
    lines = [
        "%-14s %6s %7s %8s %13s %12s %9s"
        % ("platform", "rows", "failed", "suppr.", "spend_usd", "impressions", "clicks")
    ]
    totals = result.totals_by_platform()
    grand = {"rows": 0, "rejected": 0, "suppressed": 0, "micros": 0, "impressions": 0, "clicks": 0}
    for platform in sorted(totals):
        bucket = totals[platform]
        for key in grand:
            grand[key] += bucket[key]
        lines.append(
            "%-14s %6d %7d %8d %13s %12d %9d"
            % (
                platform,
                bucket["rows"],
                bucket["rejected"],
                bucket["suppressed"],
                micros_to_usd(bucket["micros"]),
                bucket["impressions"],
                bucket["clicks"],
            )
        )
    lines.append(
        "%-14s %6d %7d %8d %13s %12d %9d"
        % (
            "TOTAL",
            grand["rows"],
            grand["rejected"],
            grand["suppressed"],
            micros_to_usd(grand["micros"]),
            grand["impressions"],
            grand["clicks"],
        )
    )
    return lines


def main(argv: list[str] | None = None) -> int:
    """Run the pipeline once and print the summary."""
    engine = create_db_engine()
    create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        result = run_pipeline(session)

    for line in format_delivery_table(result):
        print(line)
    print()
    for line in format_platform_table(result):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
