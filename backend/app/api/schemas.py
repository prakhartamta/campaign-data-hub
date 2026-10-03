"""Response models.

Spend crosses the wire as a cents-rounded Decimal, never micros, and CTR and CPC as
`Decimal | None` because both are null on a zero denominator rather than zero.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel


class Lineage(BaseModel):
    """Where one metric row came from and what was done to it."""

    delivery_id: str
    source_row: int
    raw_spend: str
    raw_spend_unit: str
    raw_currency: str
    fx_rate: str
    # Non-null only when normalization changed the value, so a value here is itself the evidence.
    raw_campaign: str | None
    raw_date: str | None


class Figures(BaseModel):
    """The metrics themselves. CTR and CPC are ratios of sums, never averages of row ratios."""

    spend_usd: Decimal
    impressions: int
    clicks: int
    ctr: Decimal | None
    cpc: Decimal | None


class Totals(Figures):
    """Figures over a set of rows, so the count of them belongs here and not on a single day."""

    rows: int


class MetricRow(Figures):
    """One campaign-day, with the lineage behind its numbers."""

    platform: str
    campaign: str
    date: dt.date
    lineage: Lineage


class MetricFilters(BaseModel):
    """The filters that produced a response, echoed back so the caller can trust what it got."""

    platform: str | None = None
    campaign: str | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None


class MetricsPage(BaseModel):
    filters: MetricFilters
    total: int
    limit: int
    offset: int
    rows: list[MetricRow]


class SummaryGroup(Totals):
    key: str
    # Always present, so a campaign row can be traced to its platform. Equal to `key` when the
    # grouping is by platform.
    platform: str
    # Always present, so a campaign row can be traced to its platform. Equal to `key` when the
    # grouping is by platform.
    platform: str


class MetricsSummary(BaseModel):
    filters: MetricFilters
    group_by: str
    totals: Totals
    groups: list[SummaryGroup]


class CheckOut(BaseModel):
    check_name: str
    level: str
    severity: str
    status: str
    rows_checked: int
    rows_failed: int
    message: str
    samples: list[dict]


class RejectedRowOut(BaseModel):
    source_row: int
    reasons: list[str]
    raw: dict
    # False when the row was fine but removed as a duplicate or by a quarantine.
    blamed: bool


class DeliveryOut(BaseModel):
    delivery_id: str
    platform: str | None
    week_start: dt.date | None
    week_end: dt.date | None
    is_missing: bool
    has_name_suffix: bool
    duplicate_of: str | None
    health: str
    health_reason: str
    rows_total: int
    rows_accepted: int
    rows_rejected: int
    rows_suppressed: int
    structural_error: str | None


class DeliveryDetailOut(DeliveryOut):
    content_hash: str | None
    checks: list[CheckOut]
    rejected_rows: list[RejectedRowOut]


class DeliveriesPage(BaseModel):
    total: int
    deliveries: list[DeliveryOut]


class RunOut(BaseModel):
    run_id: str
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    deliveries_total: int
    rows_accepted: int
    rows_rejected: int
    rows_suppressed: int
    error: str | None
