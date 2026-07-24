"""FastAPI application factory for S14Code (port 8115)."""

from __future__ import annotations

import os

from fastapi import FastAPI

from .routes import router
from .s13_client import LiveS13, RecordedS13


def create_app() -> FastAPI:
    app = FastAPI(title="S14Code — a face for the agent", version="0.1.0")

    # Live if an S13Code base URL is set and reachable; recorded otherwise.
    base = os.environ.get("S13_BASE_URL")
    app.state.recorded = RecordedS13()
    app.state.live = LiveS13(base) if base else None
    app.state.prefer_live = bool(base)

    app.include_router(router)
    return app


app = create_app()
