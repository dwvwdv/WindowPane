"""FastAPI application factory. Run with ``uvicorn worldpane_server.main:app``."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .api.routes import router
from .clock import Clock, SystemClock
from .config import Settings, get_settings
from .repositories.base import Repository
from .repositories.memory import InMemoryRepository
from .seed import DEMO_WORLD_ID, create_world_with_defaults
from .services import ServiceError, WorldService
from .simulation.provider import SimulationProvider, build_provider

log = logging.getLogger("worldpane_server")


def build_repository(settings: Settings) -> Repository:
    if settings.repository == "memory":
        return InMemoryRepository()
    from .repositories.postgres import PostgresRepository

    return PostgresRepository(settings.database_url)  # TODO(postgres)


def seed_demo(service: WorldService) -> str:
    """Create the 小白 + 小雞毛 demo world and a pairing code for it. Returns the code."""
    now = service.clock.now()
    tz = service.settings.default_timezone
    from zoneinfo import ZoneInfo

    create_world_with_defaults(
        service.repo, world_id=DEMO_WORLD_ID, name="Demo World", timezone=tz,
        created_at=now, start_date=now.astimezone(ZoneInfo(tz)).date(),
    )
    out = service.issue_pairing_code(
        DEMO_WORLD_ID, max_uses=10, code=service.settings.demo_pairing_code or None
    )
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

    if settings.seed_demo_world:
        code = seed_demo(service)
        app.state.demo_pairing_code = code
        if settings.env == "dev":
            log.warning("Demo world %s seeded; pairing code: %s", DEMO_WORLD_ID, code)

    return app


app = create_app()
