"""Pairing atomicity, archived characters in history, restart with a fixed demo code."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from worldpane_server.main import create_app
from worldpane_server.repositories.memory import InMemoryRepository
from worldpane_server.seed import DEMO_CHARACTER_IDS, DEMO_WORLD_ID

from .conftest import DEMO_CODE, TPE, auth, pair


def _break_device_insert(repo, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("device insert failed")

    if isinstance(repo, InMemoryRepository):
        monkeypatch.setattr(repo, "add_device", boom)
    else:
        monkeypatch.setattr(type(repo), "_insert_device", staticmethod(boom))


def test_failed_device_insert_does_not_burn_the_code(app, repo, monkeypatch):
    service = app.state.service
    code = service.issue_pairing_code(DEMO_WORLD_ID, max_uses=1).pairing_code
    with monkeypatch.context() as m:
        _break_device_insert(repo, m)
        with pytest.raises(RuntimeError):
            service.pair(code, None)
    # The single-use code is still usable once the failure is gone.
    creds = service.pair(code, None)
    assert creds.world_id == DEMO_WORLD_ID


def _archive(repo, character_id: str, at: datetime) -> None:
    if isinstance(repo, InMemoryRepository):
        repo.archive_character(character_id, at)
    else:
        with repo._pool.connection() as conn:
            conn.execute("update worldpane.characters set archived_at = %s where id = %s", (at, character_id))


def test_archived_character_keeps_history(client, token, repo, clock):
    clock.set(datetime(2026, 10, 7, 9, 0, tzinfo=TPE))
    q = {"date": "2026-10-06"}
    before = client.get("/api/v1/world/history", params=q, headers=auth(token)).json()
    _archive(repo, DEMO_CHARACTER_IDS[1], clock.now())

    after = client.get("/api/v1/world/history", params=q, headers=auth(token)).json()
    assert after == before  # 小雞毛's past days are still there

    state = client.get("/api/v1/device/state", headers=auth(token)).json()
    assert [c["id"] for c in state["characters"]] == [DEMO_CHARACTER_IDS[0]]


def test_restart_reuses_live_fixed_demo_code(settings, repo, clock, app):
    # ``app`` already issued DEMO_CODE for the demo world; start a second process on the same data.
    second = TestClient(create_app(settings, repository=repo, clock=clock))
    assert second.app.state.demo_pairing_code == DEMO_CODE
    assert second.get("/api/v1/device/state", headers=auth(pair(second))).status_code == 200
