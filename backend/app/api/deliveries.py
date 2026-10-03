"""The delivery endpoints: the health grid, and one delivery's checks and rejected rows."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CheckResult, Delivery, RejectedRow
from .deps import get_session
from .schemas import CheckOut, DeliveriesPage, DeliveryDetailOut, DeliveryOut, RejectedRowOut

router = APIRouter(tags=["deliveries"])


def to_summary(delivery: Delivery) -> DeliveryOut:
    """Copy the fields the grid needs off one row."""
    return DeliveryOut(
        delivery_id=delivery.delivery_id,
        platform=delivery.platform,
        week_start=delivery.week_start,
        week_end=delivery.week_end,
        is_missing=delivery.is_missing,
        has_name_suffix=delivery.has_name_suffix,
        duplicate_of=delivery.duplicate_of,
        health=delivery.health,
        health_reason=delivery.health_reason,
        rows_total=delivery.rows_total,
        rows_accepted=delivery.rows_accepted,
        rows_rejected=delivery.rows_rejected,
        rows_suppressed=delivery.rows_suppressed,
        structural_error=delivery.structural_error,
    )


@router.get("/deliveries", response_model=DeliveriesPage)
def list_deliveries(
    session: Session = Depends(get_session),
    platform: str | None = None,
    health: str | None = None,
) -> DeliveriesPage:
    """Every expected delivery, including the slots where no file arrived.

    Not paged: the grid is 16 cells by design, and a page window would let the UI render a grid
    with holes that look like missing deliveries.
    """
    statement = select(Delivery)
    if platform:
        statement = statement.where(Delivery.platform == platform)
    if health:
        statement = statement.where(Delivery.health == health)

    # By delivery_id, which sorts platform then week, so the grid order is stable across runs.
    deliveries = session.execute(statement.order_by(Delivery.delivery_id)).scalars().all()
    return DeliveriesPage(
        total=len(deliveries), deliveries=[to_summary(delivery) for delivery in deliveries]
    )


@router.get("/deliveries/{delivery_id}", response_model=DeliveryDetailOut)
def get_delivery(delivery_id: str, session: Session = Depends(get_session)) -> DeliveryDetailOut:
    """One delivery with every check that ran against it and every row it excluded."""
    delivery = session.get(Delivery, delivery_id)
    if delivery is None:
        # A named 404 rather than an empty detail page: the id came from a URL the user may have
        # typed or kept after a rename.
        raise HTTPException(status_code=404, detail=f"no delivery {delivery_id!r}")

    checks = session.execute(
        select(CheckResult)
        .where(CheckResult.delivery_id == delivery_id)
        .order_by(CheckResult.level, CheckResult.check_name)
    ).scalars()

    rejected = session.execute(
        select(RejectedRow)
        .where(RejectedRow.delivery_id == delivery_id)
        .order_by(RejectedRow.source_row)
    ).scalars()

    return DeliveryDetailOut(
        **to_summary(delivery).model_dump(),
        content_hash=delivery.content_hash,
        checks=[
            CheckOut(
                check_name=check.check_name,
                level=check.level,
                severity=check.severity,
                status=check.status,
                rows_checked=check.rows_checked,
                rows_failed=check.rows_failed,
                message=check.message,
                samples=check.samples,
            )
            for check in checks
        ],
        rejected_rows=[
            RejectedRowOut(
                source_row=row.source_row, reasons=row.reasons, raw=row.raw, blamed=row.blamed
            )
            for row in rejected
        ],
    )
