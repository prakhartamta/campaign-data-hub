"""Delivery-level checks: did the right file arrive, once, under the right name?

These are about the delivery's place in the expected grid rather than its contents, which is why
they are the only checks that have something to say about a file that never turned up.
"""

from __future__ import annotations

from .base import (
    ACTION_DROP_ROW,
    ACTION_FLAG,
    LEVEL_DELIVERY,
    SEVERITY_FAIL,
    SEVERITY_WARN,
    STATUS_FAIL,
    STATUS_WARN,
    Check,
    CheckContext,
    CheckOutcome,
    days_in,
    passed,
)


class DeliveryPresent(Check):
    """Reports an expected slot that received no file, with the row count it should have had.

    The grid is built from the schedule rather than the directory listing, which is the only way
    an absent delivery can be a finding instead of simply nothing.
    """

    name = "delivery_present"
    level = LEVEL_DELIVERY
    severity = SEVERITY_FAIL
    action = ACTION_FLAG

    def applies_to(self, context: CheckContext) -> bool:
        # The one check that exists to speak about a missing delivery.
        return True

    def run(self, context: CheckContext) -> CheckOutcome:
        if not context.is_missing:
            return passed(0, "file arrived")

        message = f"no file arrived for {context.platform} week starting "
        message += context.week.start.isoformat() if context.week else "unknown"
        if context.week:
            message += f"; {days_in(context.week)} day(s) of data absent"
        return CheckOutcome(status=STATUS_FAIL, message=message)


class FileNameMatchesConvention(Check):
    """Flags a file whose name carries anything beyond the expected platform and week.

    Worth its own warning, separate from whether the contents duplicate another delivery: a
    hand-renamed file is a process signal even when its data turns out to be fine.
    """

    name = "file_name_matches_convention"
    level = LEVEL_DELIVERY
    severity = SEVERITY_WARN
    action = ACTION_FLAG

    def applies_to(self, context: CheckContext) -> bool:
        return not context.is_missing

    def run(self, context: CheckContext) -> CheckOutcome:
        if not context.has_name_suffix:
            return passed(0, "file name matches the convention")
        expected = context.expected_filename or "<platform>_<week-start>"
        return CheckOutcome(
            status=STATUS_WARN,
            message=f"file name has something appended; expected {expected}",
        )


class DuplicateDeliveryContent(Check):
    """Reports a delivery superseded by another file in the same slot, and why it was superseded.

    Two outcomes from one situation, decided by the content hash: a byte-identical resend is a
    warning, while two files that disagree about the same week are a failure, because picking one
    silently would discard a correction.
    """

    name = "duplicate_delivery_content"
    level = LEVEL_DELIVERY
    severity = SEVERITY_WARN
    action = ACTION_DROP_ROW

    def applies_to(self, context: CheckContext) -> bool:
        return not context.is_missing

    def run(self, context: CheckContext) -> CheckOutcome:
        if context.duplicate_of is None:
            return passed(0, "this delivery is the only file for its slot")

        # The pipeline has already compared hashes and recorded a structural error on the loser
        # when the two files differed, so the presence of that error is what tells the two cases
        # apart here.
        if context.structural_error:
            return CheckOutcome(
                status=STATUS_FAIL,
                message=(
                    f"a different file already occupies this slot: {context.duplicate_of}. "
                    "The two disagree about the same week, so neither is trusted automatically."
                ),
            )
        return CheckOutcome(
            status=STATUS_WARN,
            message=(
                f"byte-identical to {context.duplicate_of}, so it was counted once. "
                "Ingested nothing from this copy."
            ),
        )
