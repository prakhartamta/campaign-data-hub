"""Paths, the expected delivery schedule, and quality thresholds.

All data, no logic: the pipeline reads the schedule and thresholds from here so no file name,
campaign name or date is written into pipeline code.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path

# --- Paths -----------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("CDH_DATA_DIR", REPO_ROOT / "data"))
DELIVERIES_DIR = DATA_DIR / "deliveries"
EXCHANGE_RATES_PATH = DATA_DIR / "exchange_rates.json"

DATABASE_URL = os.environ.get("CDH_DATABASE_URL", f"sqlite:///{REPO_ROOT / 'campaign_data_hub.db'}")

# What counts as a candidate delivery. Dotfiles are skipped too, because macOS writes
# .DS_Store into data directories and the delivery count must not depend on the host.
DELIVERY_EXTENSIONS = frozenset({".csv", ".json"})


# --- Expected delivery schedule --------------------------------------------

# Weeks are generated from these three values, not listed, so "the last week is short" falls
# out of the rule instead of being a special case.
PERIOD_START = dt.date(2026, 6, 1)
PERIOD_END = dt.date(2026, 6, 30)
WEEK_DAYS = 7


@dataclass(frozen=True)
class Week:
    """One expected delivery window, both dates inclusive.

    Frozen so a window cannot be edited after the schedule is built.
    """

    start: dt.date
    end: dt.date

    @property
    def days_covered(self) -> int:
        """Calendar days in this window, counting both ends.

        Every volume comparison divides by this instead of WEEK_DAYS, because the last week
        of a period is shorter.
        """
        return (self.end - self.start).days + 1

    def contains(self, day: dt.date) -> bool:
        """Whether a date falls inside this window."""
        return self.start <= day <= self.end


def expected_weeks(
    period_start: dt.date = PERIOD_START,
    period_end: dt.date = PERIOD_END,
    week_days: int = WEEK_DAYS,
) -> list[Week]:
    """Generate the expected delivery windows, truncating the last at the period end.

    For June 2026: 06-01, 06-08, 06-15, 06-22, and 06-29 covering only two days.
    """
    weeks = []
    start = period_start
    while start <= period_end:
        end = start + dt.timedelta(days=week_days - 1)
        if end > period_end:
            end = period_end
        weeks.append(Week(start=start, end=end))
        start = end + dt.timedelta(days=1)
    return weeks


def week_for(day: dt.date, weeks: list[Week] | None = None) -> Week | None:
    """Return the expected week containing a date, or None if it is outside the period."""
    if weeks is None:
        weeks = expected_weeks()
    for week in weeks:
        if week.contains(day):
            return week
    return None


# --- Quality thresholds ----------------------------------------------------
# Measured justification for each number: docs/findings.md sections 9 and 10.

# A delivery FAILs above this reject rate. Counts only rows rejected by a row-level validity
# check, never rows suppressed by deduplication or quarantine, so a file that is clean after
# deduplication is not reported as failing.
MAX_REJECT_RATE = 0.10

# Quarantine when a delivery's median CPM differs from its platform's other deliveries by more
# than this factor. The one defective delivery is ~103x; every clean one is within 1.2x.
SPEND_SCALE_MAX_RATIO = 10.0

# WARN when accepted rows per covered day fall outside this band. Observed range: 0.762-1.029.
ROW_VOLUME_MIN_RATIO = 0.5
ROW_VOLUME_MAX_RATIO = 2.0

# Failing-row examples kept per check. The true count always lives in rows_failed.
MAX_CHECK_SAMPLES = 5
