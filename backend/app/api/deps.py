"""Request-scoped dependencies.

The session factory is read off `app.state` rather than built here, so a test can create the app
against a temporary database without patching this module.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    """Yield one session per request and close it once the response is sent."""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
