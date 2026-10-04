"""The ingestion pipeline, called by both the CLI and the API.

Anything that needs more than one file to decide happens after parsing, which is why the quality
checks are a separate stage rather than part of an adapter.
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
from .checks.base import (
    ACTION_DROP_ROW,
    ACTION_QUARANTINE_FILE,
    ACTION_REJECT_ROW,
    Check,
    CheckContext,
    CheckOutcome,
    PlatformBaseline,
    cost_per_mille,
)
from .checks.registry import ALL_CHECKS, run_check
from .config import DELIVERIES_DIR, EXCHANGE_RATES_PATH, Week, expected_weeks
from .discovery import DiscoveredFile, Slot, discover
from .health import HealthInput, classify
from .models import CheckResult, Delivery, IngestionRun, Metric, RejectedRow
from .money import load_rates
from .normalize import apply_canonical_names, canonical_names


@dataclass
class DroppedRow:
    """A parsed row that did not reach the metrics, and why.

    `blamed` separates a row that was itself invalid from one that was merely redundant, which is
    what keeps a file that is clean after deduplication out of the reject-rate threshold.
    """

    source_row: int
    reasons: list[str]
    raw: dict
    blamed: bool


@dataclass
class DeliveryOutcome:
    """What the pipeline concluded about one delivery, whether or not a file arrived."""

    delivery_id: str
    platform: str | None
    week: Week | None
    expected_filename: str | None = None
    is_missing: bool = False
    has_name_suffix: bool = False
    content_hash: str | None = None
    duplicate_of: str | None = None
    conflicts_with: str | None = None
    structural_error: str | None = None
    is_quarantined: bool = False

    # As parsed, before any check has had a say.
    parsed: list[CanonicalRow] = field(default_factory=list)
    failures: list[ParseFailure] = field(default_factory=list)

    # After the checks.
    rows: list[CanonicalRow] = field(default_factory=list)
    dropped: list[DroppedRow] = field(default_factory=list)
    results: list[tuple[Check, CheckOutcome]] = field(default_factory=list)

    health: str = "pass"
    health_reason: str = ""

    @property
    def rows_total(self) -> int:
        return len(self.parsed) + len(self.failures)

    @property
    def rows_rejected(self) -> int:
        """Rows excluded because they were invalid. The numerator of the reject rate."""
        return len([drop for drop in self.dropped if drop.blamed])

    @property
    def rows_suppressed(self) -> int:
        """Rows excluded for a reason that is not their fault."""
        return len([drop for drop in self.dropped if not drop.blamed])

    @property
    def rows_normalized(self) -> int:
        count = 0
        for row in self.rows:
            if row.raw_campaign is not None or row.raw_date is not None:
                count += 1
        return count

    @property
    def spend_usd_micros(self) -> int:
        return sum(row.spend_usd_micros for row in self.rows)

    @property
    def impressions(self) -> int:
        return sum(row.impressions for row in self.rows)

    @property
    def clicks(self) -> int:
        return sum(row.clicks for row in self.rows)


@dataclass
class PipelineResult:
    """Everything one run produced, ordered so two runs are comparable line by line."""

    run_id: str
    outcomes: list[DeliveryOutcome]
    rows: list[CanonicalRow]

    def totals_by_platform(self) -> dict[str, dict[str, int]]:
        """Per-platform counts and totals, for the CLI summary."""
        totals: dict[str, dict[str, int]] = {}
        for outcome in self.outcomes:
            if outcome.platform is None:
                continue
            bucket = totals.setdefault(
                outcome.platform,
                {"rows": 0, "rejected": 0, "suppressed": 0, "micros": 0, "impressions": 0, "clicks": 0},
            )
            bucket["rows"] += len(outcome.rows)
            bucket["rejected"] += outcome.rows_rejected
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

    # 1. Build the expected grid and place the files on it.
    discovered = discover(deliveries_dir, adapters.platform_extensions(), weeks)

    # 2. Parse each file in isolation.
    outcomes = []
    for slot in discovered.slots:
        outcomes.extend(outcomes_for_slot(slot, registry, rates))
    for unplaced in discovered.unplaced:
        outcomes.append(outcome_for_unplaced(unplaced))
    outcomes.sort(key=lambda outcome: outcome.delivery_id)

    # 3. Resolve slots that received more than one file.
    resolve_duplicates(discovered.slots, outcomes)

    # 4. Resolve campaign identity. The vote spans deliveries, so it is counted once over every
    #    parsed row and then applied to each delivery in place.
    #    Before the checks rather than after, because a check that counts campaigns must see the
    #    real number of them: left until later, campaign_day_coverage reads "Brand Awareness Q2"
    #    and "brand awareness q2" as two campaigns and reports gaps that do not exist.
    #    Rows that a check will later reject therefore also get a vote on spelling. That is a
    #    weaker rule than voting on accepted rows only, and it changes no winner in this data,
    #    because every variant spelling is a minority of its own campaign either way.
    parsed = [row for outcome in outcomes for row in outcome.parsed]
    canonical = canonical_names(parsed)
    for outcome in outcomes:
        outcome.parsed = apply_canonical_names(outcome.parsed, canonical)

    # 5. Run the checks. A delivery is compared against its platform's other deliveries, so this
    #    needs every file parsed first.
    baselines = build_baselines(outcomes)
    for outcome in outcomes:
        apply_checks(outcome, baselines.get(outcome.delivery_id))

    # 6. Collapse to the canonical key, in memory, before anything is written.
    rows = collapse_to_key(outcomes)

    # 7. Classify health.
    for outcome in outcomes:
        outcome.health, outcome.health_reason = classify(health_input(outcome))

    # 8. Persist everything in one transaction.
    run_id = uuid.uuid4().hex
    persist(session, run_id, outcomes, rows)
    return PipelineResult(run_id=run_id, outcomes=outcomes, rows=rows)


# --- Step 2: parse ----------------------------------------------------------


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
                expected_filename=slot.expected_filename,
                is_missing=True,
            )
        ]
    return [parse_one(discovered, slot, registry, rates) for discovered in slot.files]


def parse_one(
    discovered: DiscoveredFile,
    slot: Slot | None,
    registry: dict[str, adapters.Adapter],
    rates: dict[str, Decimal],
) -> DeliveryOutcome:
    """Read and parse one delivery file, recording any failure rather than raising.

    The error-isolation boundary: one unreadable file must never stop the other fifteen.
    """
    outcome = DeliveryOutcome(
        delivery_id=discovered.delivery_id,
        platform=discovered.platform,
        week=slot.week if slot else None,
        expected_filename=slot.expected_filename if slot else None,
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

    # A header and nothing else is a truncated upload, not a quiet week: without this it would
    # pass every check, since there is no row for any of them to object to.
    if not parsed.rows and not parsed.failures:
        outcome.structural_error = "the file has no data rows"
        return outcome

    outcome.parsed = parsed.rows
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


# --- Step 3: resolve slots --------------------------------------------------


def resolve_duplicates(slots: list[Slot], outcomes: list[DeliveryOutcome]) -> None:
    """Keep one file per slot, and record whether the loser is a copy or a disagreement.

    The content hash is what tells those apart, which is why this cannot happen during discovery:
    discovery reads names, not bytes.
    """
    by_id = {outcome.delivery_id: outcome for outcome in outcomes}

    for slot in slots:
        if len(slot.files) < 2:
            continue

        # The file matching the convention wins; otherwise the first by sorted name, so the choice
        # never depends on the order the filesystem listed the directory in.
        names = sorted(file.delivery_id for file in slot.files)
        keeper = slot.expected_filename if slot.expected_filename in names else names[0]
        keeper_hash = by_id[keeper].content_hash

        for name in names:
            if name == keeper:
                continue
            loser = by_id[name]
            loser.duplicate_of = keeper
            if loser.content_hash != keeper_hash:
                loser.conflicts_with = keeper
                loser.structural_error = f"a different file already occupies this slot: {keeper}"


# --- Step 4: checks ---------------------------------------------------------


def build_baselines(outcomes: list[DeliveryOutcome]) -> dict[str, PlatformBaseline]:
    """For each delivery, the cost per mille of its platform's *other* deliveries.

    Leave-one-out, so a delivery is never judged against a line it helped draw.
    """
    per_platform: dict[str, dict[str, float]] = {}
    for outcome in outcomes:
        if outcome.platform is None or outcome.duplicate_of or not outcome.parsed:
            continue
        cpm = cost_per_mille(outcome.parsed)
        if cpm is not None:
            per_platform.setdefault(outcome.platform, {})[outcome.delivery_id] = cpm

    baselines = {}
    for platform, by_delivery in per_platform.items():
        for delivery_id in by_delivery:
            others = sorted(cpm for other, cpm in by_delivery.items() if other != delivery_id)
            baselines[delivery_id] = PlatformBaseline(platform=platform, other_cpms=others)
    return baselines


def apply_checks(outcome: DeliveryOutcome, baseline: PlatformBaseline | None) -> None:
    """Run every check against one delivery and apply the verdicts to its rows."""
    adapter = adapters.by_platform().get(outcome.platform or "")
    context = CheckContext(
        delivery_id=outcome.delivery_id,
        platform=outcome.platform,
        week=outcome.week,
        expected_filename=outcome.expected_filename,
        rows=list(outcome.parsed),
        failures=list(outcome.failures),
        is_missing=outcome.is_missing,
        has_name_suffix=outcome.has_name_suffix,
        structural_error=outcome.structural_error,
        content_hash=outcome.content_hash,
        duplicate_of=outcome.duplicate_of,
        baseline=baseline,
        date_formats=adapter.date_formats if adapter else (),
    )

    # One lookup of the original values, so a dropped row can carry its raw fields without going
    # back to two different sources later.
    raws = {failure.source_row: failure.raw for failure in outcome.failures}
    for row in outcome.parsed:
        raws[row.source_row] = raw_fields(row)

    drops: dict[int, DroppedRow] = {}
    for check in ALL_CHECKS:
        result = run_check(check, context)
        if result is None:
            continue
        # The check itself is kept, not just its severity, so its name and level come from the
        # check rather than from its position in a list.
        outcome.results.append((check, result))

        if check.action == ACTION_QUARANTINE_FILE and result.quarantine_reason:
            outcome.is_quarantined = True
        elif check.action in (ACTION_REJECT_ROW, ACTION_DROP_ROW):
            blamed = check.action == ACTION_REJECT_ROW
            for source_row, reason in result.row_reasons.items():
                record_drop(drops, source_row, reason, raws, blamed)

    # A quarantined, superseded or unreadable delivery contributes nothing, and its rows are not
    # blamed for it: they were not individually at fault.
    if outcome.is_quarantined or outcome.duplicate_of or outcome.structural_error:
        reason = outcome.structural_error or (
            f"superseded by {outcome.duplicate_of}" if outcome.duplicate_of else "delivery quarantined"
        )
        for row in outcome.parsed:
            record_drop(drops, row.source_row, reason, raws, blamed=False)
        outcome.rows = []
    else:
        outcome.rows = [row for row in outcome.parsed if row.source_row not in drops]

    outcome.dropped = [drops[source_row] for source_row in sorted(drops)]


def record_drop(
    drops: dict[int, DroppedRow],
    source_row: int,
    reason: str,
    raws: dict[int, dict],
    blamed: bool,
) -> None:
    """Record that a row was excluded, merging reasons when more than one check condemns it.

    Blame is sticky: once any validity check has rejected a row, a later suppression does not
    launder it back into the unblamed bucket.
    """
    existing = drops.get(source_row)
    if existing is None:
        drops[source_row] = DroppedRow(
            source_row=source_row,
            reasons=[reason],
            raw=raws.get(source_row, {}),
            blamed=blamed,
        )
        return
    if reason not in existing.reasons:
        existing.reasons.append(reason)
    existing.blamed = existing.blamed or blamed


def raw_fields(row: CanonicalRow) -> dict:
    """The original field values behind one canonical row, for the quality report."""
    return {
        "campaign": row.raw_campaign or row.campaign,
        "date": row.raw_date or row.date.isoformat(),
        "spend": row.raw_spend,
        "spend_unit": row.raw_spend_unit,
        "currency": row.raw_currency,
        "impressions": str(row.impressions),
        "clicks": str(row.clicks),
    }


# --- Step 6: collapse -------------------------------------------------------


def collapse_to_key(outcomes: list[DeliveryOutcome]) -> list[CanonicalRow]:
    """Collect every accepted row keyed by (platform, campaign, date), before anything is written.

    Done in memory so a key arriving twice fails loudly here, rather than as an IntegrityError
    inside the single write transaction that would roll back all sixteen deliveries and leave no
    quality report explaining why. A collision is a bug in the pipeline, not a defect in the data,
    which is why this raises rather than recording a finding.
    """
    keyed: dict[tuple, CanonicalRow] = {}
    collisions = []
    for outcome in outcomes:
        for row in outcome.rows:
            if row.key in keyed:
                collisions.append((row.key, keyed[row.key].delivery_id, row.delivery_id))
                continue
            keyed[row.key] = row

    if collisions:
        key, first, second = collisions[0]
        raise AssertionError(
            f"{len(collisions)} canonical key collision(s) across deliveries; "
            f"first: {key} appears in both {first} and {second}"
        )

    return [keyed[key] for key in sorted(keyed)]


# --- Step 7: health ---------------------------------------------------------


def health_input(outcome: DeliveryOutcome) -> HealthInput:
    """Gather the few facts the health precedence list reads."""
    return HealthInput(
        is_missing=outcome.is_missing,
        is_quarantined=outcome.is_quarantined,
        conflicts_with=outcome.conflicts_with,
        supersedes=outcome.duplicate_of if not outcome.conflicts_with else None,
        rows_total=outcome.rows_total,
        rows_rejected=outcome.rows_rejected,
        rows_suppressed=outcome.rows_suppressed,
        rows_normalized=outcome.rows_normalized,
        outcomes=[(check.level, check.severity, result) for check, result in outcome.results],
    )


# --- Step 8: persist --------------------------------------------------------


def persist(
    session: Session,
    run_id: str,
    outcomes: list[DeliveryOutcome],
    rows: list[CanonicalRow],
) -> None:
    """Replace everything this run computed, in one transaction.

    A full recompute rather than an upsert, so a delivery that stops arriving disappears instead of
    lingering, and so running twice cannot accumulate anything.
    """
    started = dt.datetime.now(dt.timezone.utc)

    session.execute(delete(Metric))
    session.execute(delete(RejectedRow))
    session.execute(delete(CheckResult))
    session.execute(delete(Delivery))

    accepted = rejected = suppressed = 0

    for outcome in outcomes:
        accepted += len(outcome.rows)
        rejected += outcome.rows_rejected
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
                health_reason=outcome.health_reason,
                rows_total=outcome.rows_total,
                rows_accepted=len(outcome.rows),
                rows_rejected=outcome.rows_rejected,
                rows_suppressed=outcome.rows_suppressed,
                structural_error=outcome.structural_error,
            )
        )

        for check, result in outcome.results:
            session.add(
                CheckResult(
                    delivery_id=outcome.delivery_id,
                    check_name=check.name,
                    level=check.level,
                    severity=check.severity,
                    status=result.status,
                    rows_checked=result.rows_checked,
                    rows_failed=result.rows_failed,
                    message=result.message,
                    samples=result.samples,
                )
            )

        for drop in outcome.dropped:
            session.add(
                RejectedRow(
                    delivery_id=outcome.delivery_id,
                    source_row=drop.source_row,
                    reasons=sorted(set(drop.reasons)),
                    raw=drop.raw,
                    blamed=drop.blamed,
                )
            )

    for row in rows:
        session.add(
            Metric(
                platform=row.platform,
                campaign=row.campaign,
                date=row.date,
                spend_usd_micros=row.spend_usd_micros,
                impressions=row.impressions,
                clicks=row.clicks,
                delivery_id=row.delivery_id,
                source_row=row.source_row,
                raw_spend=row.raw_spend,
                raw_spend_unit=row.raw_spend_unit,
                raw_currency=row.raw_currency,
                fx_rate=str(row.fx_rate),
                raw_campaign=row.raw_campaign,
                raw_date=row.raw_date,
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
