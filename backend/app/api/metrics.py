"""The metrics endpoints: daily rows with lineage, and grouped summaries.

Both share one filter set and one totals helper, so a figure in the summary cannot disagree with
the rows it summarizes.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Metric
from ..money import cost_ratio, micros_to_usd, ratio
from .deps import get_session
from .schemas import (
    Figures,
    Lineage,
    MetricFilters,
    MetricRow,
    MetricsPage,
    MetricsSummary,
    SummaryGroup,
    Totals,
)

router = APIRouter(tags=["metrics"])

GROUP_BY_CAMPAIGN = "campaign"
GROUP_BY_PLATFORM = "platform"

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


def collect_filters(
    platform: str | None,
    campaign: str | None,
    date_from: dt.date | None,
    date_to: dt.date | None,
) -> MetricFilters:
    """Gather the query parameters into the object echoed back on every response."""
    return MetricFilters(
        platform=platform, campaign=campaign, date_from=date_from, date_to=date_to
    )


def apply_filters(statement, filters: MetricFilters):
    """Narrow a metrics query. Campaign matches case-insensitively, since identity is case-folded."""
    if filters.platform:
        statement = statement.where(Metric.platform == filters.platform)
    if filters.campaign:
        statement = statement.where(func.lower(Metric.campaign) == filters.campaign.lower())
    if filters.date_from:
        statement = statement.where(Metric.date >= filters.date_from)
    if filters.date_to:
        statement = statement.where(Metric.date <= filters.date_to)
    return statement


def figures_from(micros: int, impressions: int, clicks: int) -> Figures:
    """Build the metrics from sums.

    Called with zeros for an empty result, which is why it must not special-case emptiness: the
    ratios already return None on a zero denominator.
    """
    return Figures(
        spend_usd=micros_to_usd(micros),
        impressions=impressions,
        clicks=clicks,
        ctr=ratio(clicks, impressions),
        cpc=cost_ratio(micros, clicks),
    )


def totals_from(rows: int, micros: int, impressions: int, clicks: int) -> Totals:
    """The same figures, plus how many rows produced them."""
    return Totals(rows=rows, **figures_from(micros, impressions, clicks).model_dump())


@router.get("/metrics", response_model=MetricsPage)
def list_metrics(
    session: Session = Depends(get_session),
    platform: str | None = None,
    campaign: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> MetricsPage:
    """One row per campaign-day, with the lineage behind each number.

    `total` is the count before the page window, so the caller can page without guessing.
    """
    filters = collect_filters(platform, campaign, date_from, date_to)

    total = session.execute(
        apply_filters(select(func.count()).select_from(Metric), filters)
    ).scalar_one()

    # Explicit ORDER BY on the full key: without it SQLite is free to return a different order
    # between runs, and the run-twice diff fails on row order alone.
    statement = (
        apply_filters(select(Metric), filters)
        .order_by(Metric.platform, Metric.campaign, Metric.date)
        .limit(limit)
        .offset(offset)
    )

    rows = []
    for metric in session.execute(statement).scalars():
        figures = figures_from(metric.spend_usd_micros, metric.impressions, metric.clicks)
        rows.append(
            MetricRow(
                platform=metric.platform,
                campaign=metric.campaign,
                date=metric.date,
                lineage=Lineage(
                    delivery_id=metric.delivery_id,
                    source_row=metric.source_row,
                    raw_spend=metric.raw_spend,
                    raw_spend_unit=metric.raw_spend_unit,
                    raw_currency=metric.raw_currency,
                    fx_rate=metric.fx_rate,
                    raw_campaign=metric.raw_campaign,
                    raw_date=metric.raw_date,
                ),
                **figures.model_dump(),
            )
        )

    return MetricsPage(filters=filters, total=total, limit=limit, offset=offset, rows=rows)


@router.get("/metrics/summary", response_model=MetricsSummary)
def summarize_metrics(
    session: Session = Depends(get_session),
    group_by: str = Query(GROUP_BY_CAMPAIGN, pattern=f"^({GROUP_BY_CAMPAIGN}|{GROUP_BY_PLATFORM})$"),
    platform: str | None = None,
    campaign: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> MetricsSummary:
    """Grouped and overall totals for the same filters.

    An empty result returns zeroed totals with null ratios and no groups, never a 404: the UI
    filters on a quarantined platform and would otherwise look broken.
    """
    filters = collect_filters(platform, campaign, date_from, date_to)

    # Campaign identity is (platform, campaign), the Metric primary key, so grouping by name
    # alone would merge two platforms' campaigns that happen to share a spelling.
    if group_by == GROUP_BY_CAMPAIGN:
        group_columns = [Metric.platform, Metric.campaign]
    else:
        group_columns = [Metric.platform]

    statement = apply_filters(
        select(
            *group_columns,
            func.count().label("rows"),
            func.sum(Metric.spend_usd_micros).label("micros"),
            func.sum(Metric.impressions).label("impressions"),
            func.sum(Metric.clicks).label("clicks"),
        ),
        filters,
    ).group_by(*group_columns).order_by(*group_columns)

    groups = []
    rows = micros = impressions = clicks = 0
    for record in session.execute(statement):
        key = record.campaign if group_by == GROUP_BY_CAMPAIGN else record.platform
        groups.append(
            SummaryGroup(key=key, platform=record.platform, **totals_from(
                record.rows, record.micros, record.impressions, record.clicks
            ).model_dump())
        )
        # Summed from the groups rather than queried again, so the two can never disagree.
        rows += record.rows
        micros += record.micros
        impressions += record.impressions
        clicks += record.clicks

    return MetricsSummary(
        filters=filters,
        group_by=group_by,
        totals=totals_from(rows, micros, impressions, clicks),
        groups=groups,
    )
