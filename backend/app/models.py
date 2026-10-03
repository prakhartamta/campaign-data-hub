"""SQLAlchemy table definitions.

Natural primary keys throughout, so re-ingesting the same data cannot duplicate a row at the
database level rather than only by convention in code.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Delivery(Base):
    """One expected delivery: a file that arrived, or a slot where one should have.

    Keyed by file name, so a missing delivery uses the name it was expected to arrive under.
    """

    __tablename__ = "deliveries"

    delivery_id: Mapped[str] = mapped_column(String, primary_key=True)
    platform: Mapped[str | None] = mapped_column(String)
    week_start: Mapped[dt.date | None]
    week_end: Mapped[dt.date | None]

    # True when no file arrived for this slot.
    is_missing: Mapped[bool]
    # True when the file exists but its name does not match the expected convention.
    has_name_suffix: Mapped[bool]

    # SHA-256 of the file bytes. The only way to tell a byte-identical resend from a genuine
    # conflict, and it is why that decision cannot happen during discovery.
    content_hash: Mapped[str | None] = mapped_column(String)
    # Set on the copy, pointing at the delivery it duplicates.
    duplicate_of: Mapped[str | None] = mapped_column(String)

    health: Mapped[str] = mapped_column(String)
    # The single condition that decided the health, so the UI never re-derives it and the two
    # can never disagree.
    health_reason: Mapped[str] = mapped_column(String, default="")

    # rows_total = rows_accepted + rows_rejected + rows_suppressed.
    # rejected means a row failed a validity check; suppressed means the row was fine but removed
    # by a file- or delivery-level action such as deduplication or a quarantine. Keeping them
    # apart is what stops a file that is clean after deduplication from being reported as failing.
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_accepted: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    rows_suppressed: Mapped[int] = mapped_column(Integer, default=0)

    # Set when the file could not be read or parsed at all.
    structural_error: Mapped[str | None] = mapped_column(String)


class CheckResult(Base):
    """The outcome of one quality check against one delivery.

    Keyed by (delivery, check name) so a re-run overwrites rather than appends.
    """

    __tablename__ = "check_results"

    delivery_id: Mapped[str] = mapped_column(
        ForeignKey("deliveries.delivery_id"), primary_key=True
    )
    check_name: Mapped[str] = mapped_column(String, primary_key=True)
    level: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    rows_checked: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String, default="")
    # Up to a handful of example failures, sorted, so two runs produce identical output.
    samples: Mapped[list] = mapped_column(JSON, default=list)


class Metric(Base):
    """One campaign-day of normalized metrics, with the lineage that explains it.

    Keyed by (platform, campaign, date): the grain of the canonical dataset, which is what makes
    double counting impossible rather than merely avoided.
    """

    __tablename__ = "metrics"

    platform: Mapped[str] = mapped_column(String, primary_key=True)
    campaign: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[dt.date] = mapped_column(primary_key=True)

    # Integer micro-USD, never a float and never rounded here. Rounded to cents once, in the API.
    spend_usd_micros: Mapped[int] = mapped_column(Integer)
    impressions: Mapped[int] = mapped_column(Integer)
    clicks: Mapped[int] = mapped_column(Integer)

    delivery_id: Mapped[str] = mapped_column(ForeignKey("deliveries.delivery_id"))
    source_row: Mapped[int] = mapped_column(Integer)
    raw_spend: Mapped[str] = mapped_column(String)
    # micros | usd | units. Without it this column is unreadable, because Google reports micros,
    # Meta reports dollars and LinkedIn reports EUR.
    raw_spend_unit: Mapped[str] = mapped_column(String)
    raw_currency: Mapped[str] = mapped_column(String)
    # Stored as text, because a float column would reintroduce the precision problem the whole
    # money module exists to avoid.
    fx_rate: Mapped[str] = mapped_column(String)

    # Set only when normalization changed the value, so a value here is itself the evidence that a
    # campaign name was trimmed or a date was reformatted.
    raw_campaign: Mapped[str | None] = mapped_column(String)
    raw_date: Mapped[str | None] = mapped_column(String)


class RejectedRow(Base):
    """A source row excluded from the metrics, with every reason it failed.

    Keyed by (delivery, source row) so a re-run overwrites rather than appends.
    """

    __tablename__ = "rejected_rows"

    delivery_id: Mapped[str] = mapped_column(
        ForeignKey("deliveries.delivery_id"), primary_key=True
    )
    source_row: Mapped[int] = mapped_column(Integer, primary_key=True)
    # A list: all failing checks are collected rather than short-circuited on the first.
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    # True when the row itself was invalid, false when it was excluded for a reason that is
    # not its fault, such as being a duplicate copy or belonging to a quarantined delivery.
    # Only blamed rows count towards the reject rate that can fail a delivery.
    blamed: Mapped[bool] = mapped_column(default=True)


class IngestionRun(Base):
    """One execution of the pipeline. The only table that grows.

    Deliberately holds no data any other table depends on, so two runs produce identical output
    everywhere except here.
    """

    __tablename__ = "ingestion_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    started_at: Mapped[dt.datetime]
    finished_at: Mapped[dt.datetime | None]
    status: Mapped[str] = mapped_column(String)
    deliveries_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_accepted: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    rows_suppressed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String)
