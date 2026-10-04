"""The check interface: what a check is given, what it returns, and what its verdict does.

One class per check, so adding one means writing a class and registering it, with no change
anywhere else.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from ..adapters.base import CanonicalRow, ParseFailure
from ..config import MAX_CHECK_SAMPLES, Week

# Where a check looks. Row checks see one delivery's rows, file checks see the file as a whole,
# delivery checks see its place in the expected grid.
LEVEL_ROW = "row"
LEVEL_FILE = "file"
LEVEL_DELIVERY = "delivery"

# How much a failure matters. Only a fail-severity check can make a delivery FAIL.
SEVERITY_FAIL = "fail"
SEVERITY_WARN = "warn"

# What a failure does to the data.
ACTION_REJECT_ROW = "reject_row"        # the row is invalid: exclude it and record why
ACTION_DROP_ROW = "drop_row"            # the row is fine but redundant: exclude it, do not blame it
ACTION_QUARANTINE_FILE = "quarantine_file"  # the whole delivery is untrustworthy: ingest nothing
ACTION_FLAG = "flag"                    # report it, change nothing

STATUS_PASS = "pass"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
# A check that raised. Recorded rather than propagated, so one broken check cannot stop the run.
STATUS_ERROR = "error"


@dataclass
class PlatformBaseline:
    """What a platform's other deliveries look like, for a check that needs a comparison.

    Leave-one-out by construction: a delivery is never part of its own baseline, or a single bad
    file would move the line it is being judged against.
    """

    platform: str
    # Median cost per mille of each other delivery of this platform, already sorted.
    other_cpms: list[float] = field(default_factory=list)

    @property
    def median_cpm(self) -> float | None:
        """The middle value of the other deliveries' CPMs, or None if there are none to compare."""
        if not self.other_cpms:
            return None
        middle = len(self.other_cpms) // 2
        if len(self.other_cpms) % 2 == 1:
            return self.other_cpms[middle]
        return (self.other_cpms[middle - 1] + self.other_cpms[middle]) / 2


@dataclass
class CheckContext:
    """Everything a check is allowed to look at.

    Passed as one object so adding a check never means changing a function signature.
    """

    delivery_id: str
    platform: str | None
    week: Week | None
    expected_filename: str | None
    # Rows the adapter read successfully. Row checks narrow this; they do not mutate it.
    rows: list[CanonicalRow]
    # Rows the adapter could not read at all.
    failures: list[ParseFailure]
    is_missing: bool
    has_name_suffix: bool
    structural_error: str | None
    content_hash: str | None
    duplicate_of: str | None
    baseline: PlatformBaseline | None = None
    # The platform's declared date layouts, primary first, so a check can say which layout a row
    # used and which one its file normally uses.
    date_formats: tuple[str, ...] = ()


@dataclass
class CheckOutcome:
    """One check's verdict about one delivery."""

    status: str
    rows_checked: int = 0
    rows_failed: int = 0
    message: str = ""
    # Up to MAX_CHECK_SAMPLES examples, sorted, so two runs produce identical output.
    samples: list[dict] = field(default_factory=list)
    # Source row numbers this check condemned, each with its reason. The pipeline turns these into
    # exclusions; the check itself never edits the row list.
    row_reasons: dict[int, str] = field(default_factory=dict)
    # Set by a quarantine check to explain why the whole delivery is being dropped.
    quarantine_reason: str | None = None

    @property
    def fail_rate(self) -> float:
        """Share of checked rows that failed. Derived, so it cannot disagree with the counts."""
        if self.rows_checked == 0:
            return 0.0
        return self.rows_failed / self.rows_checked


class Check:
    """Base class for every quality check."""

    name: str = ""
    level: str = LEVEL_ROW
    severity: str = SEVERITY_FAIL
    action: str = ACTION_FLAG

    def applies_to(self, context: CheckContext) -> bool:
        """Whether this check has anything to say about this delivery.

        Most checks skip a missing or unreadable delivery, because there is nothing to inspect.
        """
        return not context.is_missing and context.structural_error is None

    def run(self, context: CheckContext) -> CheckOutcome:
        """Inspect the delivery and return a verdict. Must not mutate the context."""
        raise NotImplementedError


def build_samples(entries: list[dict], sort_key: str = "source_row") -> list[dict]:
    """Take the first few failures in a stable order, for the report.

    Sorted explicitly because one delivery's rows are shuffled in the file, so read order would
    differ between runs and break the live idempotency diff.
    """
    ordered = sorted(entries, key=lambda entry: entry.get(sort_key, 0))
    return ordered[:MAX_CHECK_SAMPLES]


def passed(rows_checked: int, message: str = "") -> CheckOutcome:
    """A clean verdict, with the number of rows that were looked at."""
    return CheckOutcome(status=STATUS_PASS, rows_checked=rows_checked, message=message)


def days_in(week: Week | None) -> int:
    """Days the delivery window covers, defaulting to a week when the window is unknown."""
    if week is None:
        return 7
    return week.days_covered


def cost_per_mille(rows: list[CanonicalRow]) -> float | None:
    """Spend per thousand impressions for a set of rows, or None when there are no impressions.

    Used instead of raw spend because it is per-impression, so it does not move with how busy a
    week was or how many days it covered.
    """
    impressions = 0
    micros = 0
    for row in rows:
        impressions += row.impressions
        micros += row.spend_usd_micros
    if impressions == 0:
        return None
    return (micros / 1_000_000) / impressions * 1000


def iso(value: dt.date | None) -> str:
    """Format a date for a message, tolerating None."""
    return value.isoformat() if value else "unknown"
