"""The ingestion pipeline, called by both the CLI and the API.

Phase 1 covers steps 1 to 3 and persists deliveries; the quality checks, the metrics table and
health classification arrive in Phase 2.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import adapters
from .adapters.base import CanonicalRow, ParseFailure
from .config import DELIVERIES_DIR, EXCHANGE_RATES_PATH, Week, expected_weeks
from .discovery import DiscoveredFile, Slot, discover
from .models import Delivery, IngestionRun
from .money import load_rates

# Health values Phase 1 can justify. The full ordered precedence list arrives with the checks.
HEALTH_PASS = "pass"
HEALTH_WARN = "warn"
HEALTH_FAIL = "fail"


@dataclass
class DeliveryOutcome:
    """What the pipeline concluded about one delivery, whether or not a file arrived."""

    delivery_id: str
    platform: str | None
    week: Week | None
    is_missing: bool = False
    has_name_suffix: bool = False
    content_hash: str | None = None
    duplicate_of: str | None = None
    structural_error: str | None = None
    rows: list[CanonicalRow] = field(default_factory=list)
    failures: list[ParseFailure] = field(default_factory=list)
    # Rows that parsed cleanly but were removed by a file- or delivery-level decision.
    rows_suppressed: int = 0

    @property
    def rows_total(self) -> int:
        """Source rows seen, readable or not."""
        return len(self.rows) + len(self.failures) + self.rows_suppressed

    @property
    def spend_usd_micros(self) -> int:
        """Total spend of the rows this delivery contributes."""
        total = 0
        for row in self.rows:
            total += row.spend_usd_micros
        return total

    @property
    def impressions(self) -> int:
        total = 0
        for row in self.rows:
            total += row.impressions
        return total

    @property
    def clicks(self) -> int:
        total = 0
        for row in self.rows:
            total += row.clicks
        return total

    @property
    def health(self) -> str:
        """Provisional health. Replaced by the ordered precedence list in Phase 2."""
        if self.is_missing or self.structural_error or self.platform is None:
            return HEALTH_FAIL
        if self.failures or self.rows_suppressed or self.has_name_suffix:
            return HEALTH_WARN
        return HEALTH_PASS


@dataclass
class PipelineResult:
    """Everything one run produced, ordered so two runs are comparable line by line."""

    run_id: str
    outcomes: list[DeliveryOutcome]

    @property
    def rows(self) -> list[CanonicalRow]:
        """Every accepted row across all deliveries."""
        rows = []
        for outcome in self.outcomes:
            rows.extend(outcome.rows)
        return rows

    def totals_by_platform(self) -> dict[str, dict[str, int]]:
        """Per-platform row counts and metric totals, for the CLI summary."""
        totals: dict[str, dict[str, int]] = {}
        for outcome in self.outcomes:
            if outcome.platform is None:
                continue
            bucket = totals.setdefault(
                outcome.platform,
                {"rows": 0, "failures": 0, "suppressed": 0, "micros": 0, "impressions": 0, "clicks": 0},
            )
            bucket["rows"] += len(outcome.rows)
            bucket["failures"] += len(outcome.failures)
            bucket["suppressed"] += outcome.rows_suppressed
            bucket["micros"] += outcome.spend_usd_micros
            bucket["impressions"] += outcome.impressions
            bucket["clicks"] += outcome.clicks
        return totals


def run_pipeline(
    session: Session,
    deliveries_dir: Path = DELIVERIES_DIR,
    rates_path: Path = EXCHANGE_RATES_PATH,
    weeks: list[Week] | None = None,
) -> PipelineResult:
    """Ingest every delivery and persist the result as a full recompute in one transaction."""
    if weeks is None:
        weeks = expected_weeks()
    rates = load_rates(rates_path)
    registry = adapters.by_platform()

    # Step 1: build the expected grid and place the files on it.
    discovered = discover(deliveries_dir, adapters.platform_extensions(), weeks)

    # Step 2: parse each file in isolation.
    outcomes = []
    for slot in discovered.slots:
        outcomes.extend(outcomes_for_slot(slot, registry, rates))
    for unplaced in discovered.unplaced:
        outcomes.append(outcome_for_unplaced(unplaced))

    # Step 3: resolve slots that received more than one file.
    resolve_duplicates(discovered.slots, outcomes)

    # Sort so the CLI output and the stored rows are identical between runs regardless of the
    # order the filesystem happened to list files in.
    outcomes.sort(key=lambda outcome: outcome.delivery_id)

    run_id = uuid.uuid4().hex
    persist(session, run_id, outcomes)
    return PipelineResult(run_id=run_id, outcomes=outcomes)


def outcomes_for_slot(
    slot: Slot, registry: dict[str, adapters.Adapter], rates: dict[str, Decimal]
) -> list[DeliveryOutcome]:
    """Produce one outcome per file in a slot, or one missing-delivery outcome if it is empty."""
    if not slot.files:
        return [
            DeliveryOutcome(
                delivery_id=slot.expected_filename,
                platform=slot.platform,
                week=slot.week,
                is_missing=True,
            )
        ]

    outcomes = []
    for discovered in slot.files:
        outcomes.append(parse_one(discovered, slot.week, registry, rates))
    return outcomes


def parse_one(
    discovered: DiscoveredFile,
    week: Week | None,
    registry: dict[str, adapters.Adapter],
    rates: dict[str, Decimal],
) -> DeliveryOutcome:
    """Read and parse one delivery file, recording any failure rather than raising.

    This is the error-isolation boundary: one unreadable file must never stop the other fourteen.
    """
    outcome = DeliveryOutcome(
        delivery_id=discovered.delivery_id,
        platform=discovered.platform,
        week=week,
        has_name_suffix=discovered.has_name_suffix,
    )

    try:
        content = discovered.path.read_bytes()
    except OSError as error:
        outcome.structural_error = f"could not read the file: {error}"
        return outcome

    outcome.content_hash = hashlib.sha256(content).hexdigest()

    adapter = registry.get(discovered.platform or "")
    if adapter is None:
        outcome.structural_error = f"no adapter registered for platform {discovered.platform!r}"
        return outcome

    try:
        parsed = adapter.parse(discovered.delivery_id, content, rates)
    except Exception as error:
        # Deliberately broad. An adapter raising anything at all is a finding about that one
        # delivery, never a reason to abort the run.
        outcome.structural_error = f"{type(error).__name__}: {error}"
        return outcome

    if parsed.missing_fields:
        outcome.structural_error = "missing required fields: " + ", ".join(parsed.missing_fields)
        return outcome

    outcome.rows = parsed.rows
    outcome.failures = parsed.failures
    return outcome


def outcome_for_unplaced(discovered: DiscoveredFile) -> DeliveryOutcome:
    """Record a file that could not be placed on the grid, so it is visible rather than ignored."""
    if discovered.platform is None:
        reason = "file name does not start with a known platform prefix"
    else:
        reason = "could not read a week start from the file name"
    return DeliveryOutcome(
        delivery_id=discovered.delivery_id,
        platform=discovered.platform,
        week=None,
        has_name_suffix=discovered.has_name_suffix,
        structural_error=reason,
    )


def resolve_duplicates(slots: list[Slot], outcomes: list[DeliveryOutcome]) -> None:
    """Keep one file per slot and suppress the rest, recording which it duplicates.

    Needed because two files in one slot would otherwise both contribute rows and double-count the
    week. Whether the loser is a harmless resend or a genuine conflict is decided by comparing
    content hashes, which is information discovery does not have.
    """
    by_id = {}
    for outcome in outcomes:
        by_id[outcome.delivery_id] = outcome

    for slot in slots:
        if len(slot.files) < 2:
            continue

        # The file matching the naming convention wins; otherwise the first by sorted name, so the
        # choice never depends on the order the filesystem listed the directory in.
        names = sorted(file.delivery_id for file in slot.files)
        if slot.expected_filename in names:
            keeper = slot.expected_filename
        else:
            keeper = names[0]

        keeper_hash = by_id[keeper].content_hash
        for name in names:
            if name == keeper:
                continue
            loser = by_id[name]
            loser.rows_suppressed = len(loser.rows) + len(loser.failures)
            loser.rows = []
            loser.failures = []
            loser.duplicate_of = keeper
            if loser.content_hash != keeper_hash:
                loser.structural_error = (
                    f"a different file already occupies this slot: {keeper}. "
                    "Two files disagree about one week, so neither is trusted automatically."
                )


def persist(session: Session, run_id: str, outcomes: list[DeliveryOutcome]) -> None:
    """Replace the stored deliveries with this run's, in one transaction.

    A full recompute rather than an upsert, so a delivery that stops arriving disappears instead of
    lingering, and so re-running cannot accumulate anything.
    """
    started = dt.datetime.now(dt.timezone.utc)

    session.execute(delete(Delivery))
    accepted = 0
    rejected = 0
    suppressed = 0

    for outcome in outcomes:
        accepted += len(outcome.rows)
        rejected += len(outcome.failures)
        suppressed += outcome.rows_suppressed
        session.add(
            Delivery(
                delivery_id=outcome.delivery_id,
                platform=outcome.platform,
                week_start=outcome.week.start if outcome.week else None,
                week_end=outcome.week.end if outcome.week else None,
                is_missing=outcome.is_missing,
                has_name_suffix=outcome.has_name_suffix,
                content_hash=outcome.content_hash,
                duplicate_of=outcome.duplicate_of,
                health=outcome.health,
                rows_total=outcome.rows_total,
                rows_accepted=len(outcome.rows),
                rows_rejected=len(outcome.failures),
                rows_suppressed=outcome.rows_suppressed,
                structural_error=outcome.structural_error,
            )
        )

    session.add(
        IngestionRun(
            run_id=run_id,
            started_at=started,
            finished_at=dt.datetime.now(dt.timezone.utc),
            status="succeeded",
            deliveries_total=len(outcomes),
            rows_accepted=accepted,
            rows_rejected=rejected,
            rows_suppressed=suppressed,
        )
    )
    session.commit()
