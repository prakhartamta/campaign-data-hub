"""Row-level checks: is this one row believable?

Plausibility bounds only, never statistics. Measured on the provided data, per-campaign CPC spans
8.5x day to day, so a row-level ratio check would have to be looser than 3x to stop crying wolf,
at which point it catches nothing a bound would not. Statistics belong at file level.
"""

from __future__ import annotations

from .base import (
    ACTION_FLAG,
    ACTION_REJECT_ROW,
    LEVEL_ROW,
    SEVERITY_FAIL,
    SEVERITY_WARN,
    STATUS_FAIL,
    STATUS_WARN,
    Check,
    CheckContext,
    CheckOutcome,
    build_samples,
    iso,
    passed,
)


class RowFieldsReadable(Check):
    """Reports the rows the adapter could not read, with the field and reason for each.

    One check rather than several, because the adapter has already decided which field failed and
    why; re-deriving that from its reason strings would be guessing at its own output.
    """

    name = "row_fields_readable"
    level = LEVEL_ROW
    severity = SEVERITY_FAIL
    action = ACTION_REJECT_ROW

    def run(self, context: CheckContext) -> CheckOutcome:
        total = len(context.rows) + len(context.failures)
        if not context.failures:
            return passed(total, "every row was readable")

        reasons = {}
        samples = []
        for failure in context.failures:
            reasons[failure.source_row] = f"{failure.field}: {failure.reason}"
            samples.append(
                {
                    "source_row": failure.source_row,
                    "field": failure.field,
                    "raw_value": failure.raw_value,
                    "reason": failure.reason,
                }
            )

        fields = sorted({failure.field for failure in context.failures})
        return CheckOutcome(
            status=STATUS_FAIL,
            rows_checked=total,
            rows_failed=len(context.failures),
            message=f"{len(context.failures)} of {total} rows unreadable in: {', '.join(fields)}",
            samples=build_samples(samples),
            row_reasons=reasons,
        )


class DateWithinDeliveryWeek(Check):
    """Rejects a row whose date falls outside the week its delivery is for.

    This is the safety net for a date read the wrong way round: a wrong format declaration, or an
    epoch feed switching units, lands dates far outside the window instead of silently shifting
    them, so the whole file lights up here rather than quietly reporting the wrong days.
    """

    name = "date_within_delivery_week"
    level = LEVEL_ROW
    severity = SEVERITY_FAIL
    action = ACTION_REJECT_ROW

    def applies_to(self, context: CheckContext) -> bool:
        return super().applies_to(context) and context.week is not None

    def run(self, context: CheckContext) -> CheckOutcome:
        week = context.week
        outside = [row for row in context.rows if not week.contains(row.date)]
        if not outside:
            return passed(len(context.rows), f"all dates fall in {iso(week.start)}..{iso(week.end)}")

        reasons = {}
        samples = []
        for row in outside:
            reasons[row.source_row] = (
                f"date {iso(row.date)} is outside the delivery week "
                f"{iso(week.start)}..{iso(week.end)}"
            )
            samples.append(
                {
                    "source_row": row.source_row,
                    "campaign": row.campaign,
                    "date": iso(row.date),
                    "raw_date": row.raw_date,
                }
            )

        return CheckOutcome(
            status=STATUS_FAIL,
            rows_checked=len(context.rows),
            rows_failed=len(outside),
            message=(
                f"{len(outside)} of {len(context.rows)} rows fall outside "
                f"{iso(week.start)}..{iso(week.end)}"
            ),
            samples=build_samples(samples),
            row_reasons=reasons,
        )


class RowValuesNormalized(Check):
    """Flags rows whose values had to be cleaned up before use, without excluding them.

    A warning rather than a rejection, because the fix needed no guessing: trimming whitespace,
    folding case, or reading a date in the platform's secondary format all preserve the value.
    """

    name = "row_values_normalized"
    level = LEVEL_ROW
    severity = SEVERITY_WARN
    action = ACTION_FLAG

    def run(self, context: CheckContext) -> CheckOutcome:
        samples = []
        campaigns = 0
        dates = 0
        for row in context.rows:
            if row.raw_campaign is not None:
                campaigns += 1
                samples.append(
                    {
                        "source_row": row.source_row,
                        "field": "campaign",
                        "raw_value": row.raw_campaign,
                        "normalized_to": row.campaign,
                    }
                )
            if row.raw_date is not None:
                dates += 1
                samples.append(
                    {
                        "source_row": row.source_row,
                        "field": "date",
                        "raw_value": row.raw_date,
                        "normalized_to": iso(row.date),
                    }
                )

        if not samples:
            return passed(len(context.rows), "no row needed normalizing")

        parts = []
        if campaigns:
            parts.append(f"{campaigns} campaign name(s)")
        if dates:
            parts.append(f"{dates} date(s)")
        return CheckOutcome(
            status=STATUS_WARN,
            rows_checked=len(context.rows),
            rows_failed=len(samples),
            message="normalized " + " and ".join(parts),
            samples=build_samples(samples),
        )


class MetricsNonNegative(Check):
    """Rejects a row whose spend, impressions or clicks is below zero.

    A negative metric means the row is not a day of delivery but a refund or an adjustment, and
    summing it with real days understates the total. Excluding it moves reported spend up, not
    down, which is why it is reported rather than quietly applied.
    """

    name = "metrics_non_negative"
    level = LEVEL_ROW
    severity = SEVERITY_FAIL
    action = ACTION_REJECT_ROW

    def run(self, context: CheckContext) -> CheckOutcome:
        reasons = {}
        samples = []
        negative_spend = 0
        negative_impressions = 0
        negative_clicks = 0
        for row in context.rows:
            offending = []
            if row.spend_usd_micros < 0:
                negative_spend += 1
                offending.append(f"spend {row.raw_spend}")
            if row.impressions < 0:
                negative_impressions += 1
                offending.append(f"impressions {row.impressions}")
            if row.clicks < 0:
                negative_clicks += 1
                offending.append(f"clicks {row.clicks}")
            if not offending:
                continue

            # One reason per row, because the pipeline keys exclusions by source row.
            reasons[row.source_row] = "negative " + ", ".join(offending)
            samples.append(
                {
                    "source_row": row.source_row,
                    "campaign": row.campaign,
                    "date": iso(row.date),
                    "spend_usd_micros": row.spend_usd_micros,
                    "impressions": row.impressions,
                    "clicks": row.clicks,
                }
            )

        if not reasons:
            return passed(len(context.rows), "no negative spend, impressions or clicks")

        parts = []
        if negative_spend:
            parts.append(f"{negative_spend} spend")
        if negative_impressions:
            parts.append(f"{negative_impressions} impressions")
        if negative_clicks:
            parts.append(f"{negative_clicks} clicks")
        return CheckOutcome(
            status=STATUS_FAIL,
            rows_checked=len(context.rows),
            rows_failed=len(reasons),
            message=(
                f"{len(reasons)} of {len(context.rows)} rows rejected for negative "
                f"metrics: {', '.join(parts)}"
            ),
            samples=build_samples(samples),
            row_reasons=reasons,
        )


class ClicksNotAboveImpressions(Check):
    """Rejects a row with more clicks than impressions.

    Impossible rather than merely odd, so it needs no threshold. It catches a column swap or
    field misalignment in part of a file, which leaves the file-level median intact and would
    otherwise be ingested and reported as a CTR above 100%.
    """

    name = "clicks_not_above_impressions"
    level = LEVEL_ROW
    severity = SEVERITY_FAIL
    action = ACTION_REJECT_ROW

    def run(self, context: CheckContext) -> CheckOutcome:
        reasons = {}
        samples = []
        for row in context.rows:
            if row.clicks <= row.impressions:
                continue

            reasons[row.source_row] = f"{row.clicks} clicks on {row.impressions} impressions"
            samples.append(
                {
                    "source_row": row.source_row,
                    "campaign": row.campaign,
                    "date": iso(row.date),
                    "impressions": row.impressions,
                    "clicks": row.clicks,
                }
            )

        if not reasons:
            return passed(len(context.rows), "no row has more clicks than impressions")

        return CheckOutcome(
            status=STATUS_FAIL,
            rows_checked=len(context.rows),
            rows_failed=len(reasons),
            message=(
                f"{len(reasons)} of {len(context.rows)} rows rejected for more clicks "
                f"than impressions"
            ),
            samples=build_samples(samples),
            row_reasons=reasons,
        )
