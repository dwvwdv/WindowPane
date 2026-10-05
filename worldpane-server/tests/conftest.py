from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from worldpane_server.clock import FixedClock
from worldpane_server.config import Settings
from worldpane_server.main import create_app
from worldpane_server.repositories.memory import InMemoryRepository

TPE = ZoneInfo("Asia/Taipei")
DEMO_CODE = "123456"
# Monday evening in the World timezone.
NOW = datetime(2026, 10, 5, 18, 42, 10, tzinfo=TPE)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        pairing_code_secret="test-secret",
        pairing_code_ttl_seconds=600,
        pairing_code_max_uses=1,
        seed_demo_world=True,
        demo_pairing_code=DEMO_CODE,
    )


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


# Every API test runs against the in-memory repository, and also against Postgres when
# WORLDPANE_TEST_DATABASE_URL points at a THROWAWAY database with supabase/migrations applied.
# Each test wipes it and re-applies supabase/seed.sql.
TEST_DATABASE_URL = os.environ.get("WORLDPANE_TEST_DATABASE_URL", "")
SEED_SQL = Path(__file__).resolve().parents[2] / "supabase" / "seed.sql"
_REPOS = ["memory"] + (["postgres"] if TEST_DATABASE_URL else [])


@pytest.fixture(scope="session")
def _pg_repo():
    from worldpane_server.repositories.postgres import PostgresRepository

    repo = PostgresRepository(TEST_DATABASE_URL, max_size=4)
    yield repo
    repo.close()


def _reset_postgres(repo) -> None:
    with repo._pool.connection() as conn:
        conn.execute(
            """delete from worldpane.device_inputs;
               delete from worldpane.pairing_codes;
               delete from worldpane.devices;
               delete from worldpane.worlds;
               delete from worldpane.character_profiles where world_id is not null;
               delete from worldpane.event_definitions;"""
        )
        conn.execute(SEED_SQL.read_text(encoding="utf-8"))


@pytest.fixture(params=_REPOS)
def repo(request):
    if request.param == "memory":
        return InMemoryRepository()
    pg = request.getfixturevalue("_pg_repo")
    _reset_postgres(pg)
    return pg


@pytest.fixture
def app(settings, clock, repo):
    return create_app(settings, repository=repo, clock=clock)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def pair(client: TestClient, code: str = DEMO_CODE) -> str:
    r = client.post("/api/v1/device/pair", json={"pairing_code": code})
    assert r.status_code == 201, r.text
    return r.json()["device_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def token(client) -> str:
    return pair(client)
