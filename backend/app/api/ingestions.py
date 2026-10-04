"""The ingestion endpoint: trigger a run and return its summary.

The pipeline is a full recompute inside one transaction, so two concurrent runs would delete each
other's rows. A non-blocking lock turns the second request into a 409 instead.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models import IngestionRun
from ..pipeline import run_pipeline
from .deps import get_session
from .schemas import RunOut

router = APIRouter(tags=["ingestions"])

# Process-wide, not per-request. The handler below is `def`, not `async def`, so FastAPI runs it
# in the threadpool and a second request genuinely arrives while the first still holds this.
ingestion_lock = threading.Lock()


def to_run_out(run: IngestionRun) -> RunOut:
    """Copy one run record into its response shape."""
    return RunOut(
        run_id=run.run_id,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        deliveries_total=run.deliveries_total,
        rows_accepted=run.rows_accepted,
        rows_rejected=run.rows_rejected,
        rows_suppressed=run.rows_suppressed,
        error=run.error,
    )


@router.post("/ingestions", response_model=RunOut, status_code=201)
def start_ingestion(session: Session = Depends(get_session)) -> RunOut:
    """Re-ingest every delivery and return the run's summary.

    Synchronous: the run takes well under a second on this dataset, and a background task would
    mean the frontend had nothing to refetch when the mutation resolved.
    """
    if not ingestion_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="an ingestion is already running")
    try:
        result = run_pipeline(session)
    finally:
        ingestion_lock.release()

    run = session.get(IngestionRun, result.run_id)
    return to_run_out(run)
