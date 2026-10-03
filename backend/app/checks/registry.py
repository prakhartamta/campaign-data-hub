"""The check registry, and the wrapper that keeps one broken check from stopping the run.

Adding a check means importing it and adding it to ALL_CHECKS. Nothing else changes.
"""

from __future__ import annotations

from .base import STATUS_ERROR, Check, CheckContext, CheckOutcome
from .delivery import DeliveryPresent, DuplicateDeliveryContent, FileNameMatchesConvention
from .file import (
    CampaignDayCoverage,
    DuplicateRowsWithinFile,
    FileStructureValid,
    SpendScaleVsPlatformBaseline,
)
from .row import (
    ClicksNotAboveImpressions,
    DateWithinDeliveryWeek,
    MetricsNonNegative,
    RowFieldsReadable,
    RowValuesNormalized,
)

# Order matters only for readability of the report; each check is independent.
ALL_CHECKS: list[Check] = [
    RowFieldsReadable(),
    DateWithinDeliveryWeek(),
    RowValuesNormalized(),
    MetricsNonNegative(),
    ClicksNotAboveImpressions(),
    FileStructureValid(),
    DuplicateRowsWithinFile(),
    SpendScaleVsPlatformBaseline(),
    CampaignDayCoverage(),
    DeliveryPresent(),
    FileNameMatchesConvention(),
    DuplicateDeliveryContent(),
]


def run_check(check: Check, context: CheckContext) -> CheckOutcome | None:
    """Run one check, turning any exception into an error verdict instead of letting it escape.

    Error isolation per NFR-2: a check with a bug must show up as a red check on that delivery,
    never as a failed run. An errored check is treated as having failed at its declared severity,
    so a crash cannot leave a delivery looking clean.
    """
    try:
        if not check.applies_to(context):
            return None
        return check.run(context)
    except Exception as error:
        return CheckOutcome(
            status=STATUS_ERROR,
            message=f"check raised {type(error).__name__}: {error}",
        )
