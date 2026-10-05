from __future__ import annotations

from datetime import datetime
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


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


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
