"""The FastAPI application factory.

A factory rather than a module-level app alone, so a test can point the whole API at a temporary
database. The engine lives on `app.state` and every route reaches it through `get_session`.

Run it with: uvicorn app.api.app:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import Engine

from ..db import create_all, create_db_engine, create_session_factory
from . import deliveries, ingestions, metrics
from .errors import register_error_handlers

API_PREFIX = "/api/v1"


def create_app(engine: Engine | None = None) -> FastAPI:
    """Build the application. Pass an engine to run against something other than the real file."""
    application = FastAPI(
        title="Campaign Data Hub",
        version="1",
        description="Daily campaign metrics with the lineage and quality checks behind them.",
    )

    engine = engine if engine is not None else create_db_engine()
    create_all(engine)
    application.state.engine = engine
    application.state.session_factory = create_session_factory(engine)

    register_error_handlers(application)

    @application.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        """Liveness, outside the versioned prefix.

        Deliberately does not touch the database: this answers "is the process up", and a probe
        that failed while SQLite held a write would restart a container that was working fine.
        """
        return {"status": "ok"}

    for module in (metrics, deliveries, ingestions):
        application.include_router(module.router, prefix=API_PREFIX)

    return application


app = create_app()
