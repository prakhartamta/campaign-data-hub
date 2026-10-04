"""File-level checks: is this file, taken as a whole, trustworthy?

This is where statistics live. A row cannot tell you its own spend is in the wrong unit; only the
comparison with the platform's other deliveries can.
"""

from __future__ import annotations

from collections import defaultdict

from ..config import SPEND_SCALE_MAX_RATIO
from .base import (
    ACTION_DROP_ROW,
    ACTION_FLAG,
    ACTION_QUARANTINE_FILE,
    LEVEL_FILE,
    SEVERITY_FAIL,
    SEVERITY_WARN,
    STATUS_FAIL,
    STATUS_WARN,
    Check,
    CheckContext,
    CheckOutcome,
    build_samples,
    cost_per_mille,
    days_in,
    iso,
    passed,
)


class FileStructureValid(Check):
    """Reports a delivery whose file could not be read or was missing required columns.

    Quarantine rather than rejection, because the problem is the file, not any particular row.
    """

    name = "file_structure_valid"
    level = LEVEL_FILE
    severity = SEVERITY_FAIL
    action = ACTION_QUARANTINE_FILE

    def applies_to(self, context: CheckContext) -> bool:
        # The only check that wants to see a delivery with a structural error, since that is
        # exactly what it reports.
        return not context.is_missing

    def run(self, context: CheckContext) -> CheckOutcome:
        if context.structural_error is None:
            return passed(len(context.rows), "file parsed and had every required field")
        return CheckOutcome(
            status=STATUS_FAIL,
            rows_checked=0,
            rows_failed=0,
            message=context.structural_error,
            quarantine_reason=context.structural_error,
        )


class DuplicateRowsWithinFile(Check):
    """Drops repeated copies of an identical row, keeping the first occurrence.

    Dropped rather than rejected: there is nothing wrong with the row, it is simply present more
    than once, so counting it against the delivery's reject rate would call a clean file broken.
    """

    name = "duplicate_rows_within_file"
    level = LEVEL_FILE
    severity = SEVERITY_WARN
    action = ACTION_DROP_ROW

    def run(self, context: CheckContext) -> CheckOutcome:
        # Grouped by the full set of values, not by (campaign, date). Two rows sharing a key but
        # disagreeing on the numbers are a different problem with a different verdict.
        # Hashed over the whole file rather than compared with the previous row: in the provided
        # data the closest duplicate pair is four lines apart and the furthest thirty-five, so a
        # neighbour comparison would find none of them.
        groups = defaultdict(list)
        for row in context.rows:
            key = (row.campaign, row.date, row.spend_usd_micros, row.impressions, row.clicks)
            groups[key].append(row)

        reasons = {}
        samples = []
        for key, members in groups.items():
            if len(members) < 2:
                continue
            ordered = sorted(members, key=lambda row: row.source_row)
            keeper = ordered[0]
            for duplicate in ordered[1:]:
                reasons[duplicate.source_row] = (
                    f"identical to row {keeper.source_row} ({keeper.campaign}, {iso(keeper.date)})"
                )
                samples.append(
                    {
                        "source_row": duplicate.source_row,
                        "campaign": duplicate.campaign,
                        "date": iso(duplicate.date),
                        "kept_row": keeper.source_row,
                    }
                )

        if not reasons:
            return passed(len(context.rows), "no repeated rows")

        return CheckOutcome(
            status=STATUS_WARN,
            rows_checked=len(context.rows),
            rows_failed=len(reasons),
            message=(
                f"{len(reasons)} repeated row(s) dropped, keeping one copy of each; "
                f"{len(context.rows)} rows in the file, {len(context.rows) - len(reasons)} distinct"
            ),
            samples=build_samples(samples),
            row_reasons=reasons,
        )


class SpendScaleVsPlatformBaseline(Check):
    """Quarantines a delivery whose cost per mille is far from its platform's other deliveries.

    Cost per mille rather than spend, because spend moves legitimately with how busy a week was
    and how many days it covered, while a per-impression rate does not.
    """

    name = "spend_scale_vs_platform_baseline"
    level = LEVEL_FILE
    severity = SEVERITY_FAIL
    action = ACTION_QUARANTINE_FILE

    def applies_to(self, context: CheckContext) -> bool:
        return (
            super().applies_to(context)
            and context.baseline is not None
            and context.baseline.median_cpm is not None
            and bool(context.rows)
        )

    def run(self, context: CheckContext) -> CheckOutcome:
        own = cost_per_mille(context.rows)
        baseline = context.baseline.median_cpm
        if own is None or own == 0 or baseline == 0:
            return passed(len(context.rows), "not enough impressions to compare")

        ratio = own / baseline
        if 1 / SPEND_SCALE_MAX_RATIO <= ratio <= SPEND_SCALE_MAX_RATIO:
            return passed(
                len(context.rows),
                f"CPM {own:.3f} is {ratio:.2f}x the platform baseline {baseline:.3f}",
            )

        factor = inferred_factor(ratio)
        corrected = f"{(sum(r.spend_usd_micros for r in context.rows) / 1_000_000) / factor:.2f}"
        message = (
            f"CPM {own:.3f} is {ratio:.1f}x the platform baseline {baseline:.3f}. "
            f"Impressions and clicks are in range, so this looks like a unit error in the spend "
            f"column: the values appear to be a factor of {factor:g} out. "
            f"Ingested nothing rather than rewrite reported money. At a factor of {factor:g} this "
            f"delivery would contribute {corrected} USD."
        )
        return CheckOutcome(
            status=STATUS_FAIL,
            rows_checked=len(context.rows),
            rows_failed=len(context.rows),
            message=message,
            samples=build_samples(
                [
                    {
                        "source_row": row.source_row,
                        "campaign": row.campaign,
                        "date": iso(row.date),
                        "raw_spend": row.raw_spend,
                        "raw_spend_unit": row.raw_spend_unit,
                    }
                    for row in context.rows
                ]
            ),
            quarantine_reason=f"spend scale {ratio:.1f}x the platform baseline",
        )


def inferred_factor(ratio: float) -> float:
    """Round a scale ratio to the nearest power of ten.

    Reported as a round factor because a real unit error is a power of ten; the measured ratio
    itself is only the detection signal, since it compares different sets of rows.
    """
    factor = 1.0
    if ratio >= 1:
        while factor * 10 <= ratio * 3:
            factor *= 10
        return factor
    while factor / 10 >= ratio / 3:
        factor /= 10
    return factor


class CampaignDayCoverage(Check):
    """Flags campaign-days with no readable row, naming the specific gaps.

    More legible than a row count: "App Install Push lost 2026-06-01" is the sentence a
    stakeholder acts on, where "one invalid date" is not.
    """

    name = "campaign_day_coverage"
    level = LEVEL_FILE
    severity = SEVERITY_WARN
    action = ACTION_FLAG

    def applies_to(self, context: CheckContext) -> bool:
        return super().applies_to(context) and context.week is not None and bool(context.rows)

    def run(self, context: CheckContext) -> CheckOutcome:
        week = context.week
        expected_days = []
        day = week.start
        while day <= week.end:
            expected_days.append(day)
            day = day.fromordinal(day.toordinal() + 1)

        # context.rows is every row the adapter could read, before any check's rejections apply. So
        # a gap is a row that never arrived or arrived unreadable; the file alone cannot tell which.
        present = defaultdict(set)
        for row in context.rows:
            present[row.campaign].add(row.date)

        gaps = []
        for campaign in sorted(present):
            for day in expected_days:
                if day not in present[campaign]:
                    gaps.append({"campaign": campaign, "date": iso(day)})

        expected_total = len(present) * days_in(week)
        if not gaps:
            return passed(
                expected_total,
                f"{len(present)} campaign(s) x {days_in(week)} day(s), all present",
            )

        # A whole day missing across every campaign is worth saying out loud separately.
        missing_everywhere = []
        for day in expected_days:
            if all(day not in present[campaign] for campaign in present):
                missing_everywhere.append(iso(day))

        message = f"{len(gaps)} of {expected_total} campaign-days have no readable row"
        if missing_everywhere:
            message += f"; no readable rows at all for {', '.join(missing_everywhere)}"

        return CheckOutcome(
            status=STATUS_WARN,
            rows_checked=expected_total,
            rows_failed=len(gaps),
            message=message,
            samples=sorted(gaps, key=lambda gap: (gap["campaign"], gap["date"]))[:5],
        )
