"""Health classification: one ordered list of conditions, first match wins.

Ordered rather than a set of independent rules, because the conditions overlap and an unordered
version contradicts itself. Two examples from the provided data: the Google delivery with repeated
rows is 8 of 43 rows removed, which reads as 18.6% and would FAIL under a reject-rate rule
although the file is complete and correct once the copies are dropped; and the superseded resend
has nothing ingested at all, which reads as 100% and would FAIL although it is a harmless copy.
"""

from __future__ import annotations

from dataclasses import dataclass

from .checks.base import (
    LEVEL_ROW,
    SEVERITY_FAIL,
    SEVERITY_WARN,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_WARN,
    CheckOutcome,
)
from .config import MAX_REJECT_RATE

HEALTH_PASS = "pass"
HEALTH_WARN = "warn"
HEALTH_FAIL = "fail"


@dataclass
class HealthInput:
    """The facts the precedence list reads. Deliberately small."""

    is_missing: bool
    is_quarantined: bool
    # Set when another file already holds this slot and the two disagree.
    conflicts_with: str | None
    # Set when another file already holds this slot and the two are byte-identical.
    supersedes: str | None
    rows_total: int
    rows_rejected: int
    rows_suppressed: int
    rows_normalized: int
    # Every check verdict, with the level and severity the check declared.
    outcomes: list[tuple[str, str, CheckOutcome]]


def classify(facts: HealthInput) -> tuple[str, str]:
    """Return the delivery's health and the one-line reason it was given.

    The reason is returned alongside the verdict so the UI never has to re-derive why a delivery is
    red, and so the two can never disagree.
    """
    # 1. Nothing arrived, so there is nothing to judge.
    if facts.is_missing:
        return HEALTH_FAIL, "no file arrived for this slot"

    # 2. The file arrived but was not trustworthy enough to ingest.
    if facts.is_quarantined:
        return HEALTH_FAIL, "quarantined, so no rows were ingested"

    # 3. Two files claim the same week and disagree. Picking one silently would hide a correction.
    if facts.conflicts_with:
        return HEALTH_FAIL, f"a different file already occupies this slot: {facts.conflicts_with}"

    # 4. A byte-identical copy. Counted once, and the copy is reported rather than hidden.
    if facts.supersedes:
        return HEALTH_WARN, f"byte-identical copy of {facts.supersedes}, counted once"

    # 5. A check about the delivery as a whole has failed, or crashed. Crashing counts, because
    #    otherwise a broken check leaves the delivery looking clean, which is the exact failure
    #    this system exists to prevent.
    #    Row-level checks are excluded here on purpose. Their job is to reject individual rows,
    #    and how many rows a delivery may lose before it stops being usable is condition 6.
    #    Failing the delivery on the first unreadable row would make that threshold dead code.
    for level, severity, outcome in facts.outcomes:
        if level == LEVEL_ROW:
            continue
        if severity == SEVERITY_FAIL and outcome.status in (STATUS_FAIL, STATUS_ERROR):
            return HEALTH_FAIL, outcome.message or "a required check failed"

    # 6. Individually invalid rows, above the tolerated share. Only rows rejected by a validity
    #    check count here; rows merely suppressed as duplicates do not, which is what keeps
    #    condition 4 and this one from contradicting each other.
    if facts.rows_total and facts.rows_rejected / facts.rows_total > MAX_REJECT_RATE:
        share = facts.rows_rejected / facts.rows_total
        return HEALTH_FAIL, (
            f"{facts.rows_rejected} of {facts.rows_total} rows rejected "
            f"({share:.1%}, above the {MAX_REJECT_RATE:.0%} threshold)"
        )

    # 7. Something was wrong but the delivery is still usable.
    for level, severity, outcome in facts.outcomes:
        if severity == SEVERITY_WARN and outcome.status in (STATUS_WARN, STATUS_ERROR):
            return HEALTH_WARN, outcome.message or "a check raised a warning"
    if facts.rows_rejected:
        return HEALTH_WARN, f"{facts.rows_rejected} row(s) rejected"
    if facts.rows_suppressed:
        return HEALTH_WARN, f"{facts.rows_suppressed} row(s) suppressed"
    if facts.rows_normalized:
        return HEALTH_WARN, f"{facts.rows_normalized} row(s) normalized"

    # 8. Nothing to report.
    return HEALTH_PASS, "no problems found"


def worst(healths: list[str]) -> str:
    """The worst health among several deliveries, for a grid cell that holds more than one.

    The grid has one cell per expected slot but health is classified per delivery, so a slot
    holding an original and a resend needs a defined colour rather than an arbitrary one.
    """
    if HEALTH_FAIL in healths:
        return HEALTH_FAIL
    if HEALTH_WARN in healths:
        return HEALTH_WARN
    return HEALTH_PASS
