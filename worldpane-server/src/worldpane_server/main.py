"""FastAPI application factory. Run with ``uvicorn worldpane_server.main:app``."""

from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from worldpane_core.catalog import official_definitions

from . import __version__
from .api.routes import router
from .clock import Clock, SystemClock
from .config import Settings, get_settings
from .repositories.base import Repository
from .repositories.memory import InMemoryRepository
from .seed import (
    DEMO_CHARACTER_IDS,
    DEMO_START_DATE,
    DEMO_WORLD_ID,
    create_world_with_defaults,
    official_default_characters,
    official_profiles,
)
from .security import hash_pairing_code
from .services import ServiceError, WorldService
from .simulation.provider import SimulationProvider, build_provider

log = logging.getLogger("worldpane_server")


@lru_cache(maxsize=4)
def _demo_document(start: date, timezone: str) -> str:
    from .demo import demo_payload, page_document

    return page_document(demo_payload(start, 7, timezone))


def build_repository(settings: Settings) -> Repository:
    if settings.repository == "memory":
        return InMemoryRepository()
    from .repositories.postgres import PostgresRepository

    return PostgresRepository(settings.database_url)


def seed_demo(service: WorldService) -> str:
    """Ensure the 小白 + 小雞毛 demo world exists and issue a pairing code for it.

    With Postgres the world usually already exists (``supabase/seed.sql``); it is reused.
    """
    if service.repo.get_world(DEMO_WORLD_ID) is None:
        try:
            create_world_with_defaults(
                service.repo, world_id=DEMO_WORLD_ID, name="窗間 Demo",
                timezone=service.settings.default_timezone, created_at=service.clock.now(),
                start_date=DEMO_START_DATE,
                characters=official_default_characters(DEMO_WORLD_ID, DEMO_CHARACTER_IDS),
            )
        except ValueError:
            # Another worker created it between our check and insert; theirs is identical.
            if service.repo.get_world(DEMO_WORLD_ID) is None:
                raise
    fixed = service.settings.demo_pairing_code or None
    try:
        out = service.issue_pairing_code(DEMO_WORLD_ID, max_uses=10, code=fixed)
    except ValueError:
        # Restart with a persistent DB: the fixed demo code may still be live. Reuse it if it
        # belongs to the demo world; never hijack a code another world is using.
        live = service.repo.get_pairing_code_by_hash(
            hash_pairing_code(fixed or "", service.settings.pairing_code_secret)
        )
        if live is None or live.world_id != DEMO_WORLD_ID:
            raise
        return fixed or ""
    return out.pairing_code


def create_app(
    settings: Settings | None = None,
    *,
    repository: Repository | None = None,
    simulation: SimulationProvider | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    service = WorldService(
        repo=repository or build_repository(settings),
        sim=simulation or build_provider(settings.simulation_provider),
        settings=settings,
        clock=clock or SystemClock(),
    )

    app = FastAPI(
        title="Worldpane API",
        version=__version__,
        description=(
            "Worldpane (窗間) backend. Devices poll `GET /api/v1/device/state` (~15 s) with "
            "`If-None-Match`; the Backend is the single source of truth for World state."
        ),
    )
    app.state.service = service
    app.state.settings = settings

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content={"detail": {"code": exc.code, "message": exc.message}})

    @app.get("/healthz", tags=["meta"], include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)

    @app.get("/demo", include_in_schema=False, response_class=HTMLResponse)
    def demo_page() -> HTMLResponse:
        # A week of the demo world from today (World-local), plus a live mode that pairs with
        # this server. Computed in memory; it never touches the configured repository.
        today = service.clock.now().astimezone(ZoneInfo(settings.default_timezone)).date()
        return HTMLResponse(_demo_document(max(today, DEMO_START_DATE), settings.default_timezone))

    # A database created from migrations only (e.g. `supabase db push`, no seed.sql) still gets
    # the official catalog and profile templates as global rows; existing rows are kept as-is.
    service.repo.install_official_content(official_definitions(), official_profiles())

    if settings.seed_demo_world:
        code = seed_demo(service)
        app.state.demo_pairing_code = code
        if settings.env == "dev":
            log.warning("Demo world %s seeded; pairing code: %s", DEMO_WORLD_ID, code)

    return app


app = create_app()
