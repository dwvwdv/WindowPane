from __future__ import annotations

from datetime import datetime, timedelta

from worldpane_server.domain import Character
from worldpane_server.security import new_id
from worldpane_server.seed import DEMO_WORLD_ID, create_world_with_defaults, official_profile

from .conftest import NOW, TPE, auth, pair

STATE_KEYS = {"server_time", "revision", "world_id", "characters"}
CHAR_KEYS = {"id", "appearance", "scene", "activity", "started_at", "ends_at"}


def test_state_shape(client, token):
    r = client.get("/api/v1/device/state", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == STATE_KEYS
    assert body["world_id"] == DEMO_WORLD_ID
    assert isinstance(body["revision"], int)
    assert body["server_time"] == "2026-10-05T18:42:10+08:00"
    assert [c["appearance"] for c in body["characters"]] == ["xiaobai", "xiaojimao"]
    for c in body["characters"]:
        assert set(c) == CHAR_KEYS
        start = datetime.fromisoformat(c["started_at"])
        end = datetime.fromisoformat(c["ends_at"])
        assert start.utcoffset() == timedelta(hours=8)
        assert start <= NOW < end
        assert c["scene"] and c["activity"]


def test_state_character_count_is_not_fixed(client, app, clock):
    """Worlds with 1 and 3 characters work through the same API (spec §31 #7)."""
    service = app.state.service
    for n in (1, 3):
        wid = new_id()
        chars = [
            Character(id=new_id(), world_id=wid, appearance_key=f"custom_{i}", display_name=f"C{i}",
                      profile=official_profile("official.freelancer.v1"), sort_order=i)
            for i in range(n)
        ]
        create_world_with_defaults(service.repo, world_id=wid, name=wid, timezone="Asia/Taipei",
                                   created_at=clock.now(), start_date=NOW.date(), characters=chars)
        code = service.issue_pairing_code(wid).pairing_code
        body = client.get("/api/v1/device/state", headers=auth(pair(client, code))).json()
        assert body["world_id"] == wid
        assert [c["id"] for c in body["characters"]] == [c.id for c in chars]


def test_shared_event_has_same_activity_for_all(client, app, token, clock):
    service = app.state.service
    world = service.repo.get_world(DEMO_WORLD_ID)
    characters = service.repo.list_characters(DEMO_WORLD_ID)
    shared = None
    for day in range(5, 20):
        events = service.ensure_plan(world, NOW.date().replace(day=day))
        shared = next((e for e in events if len(e.participant_ids) == len(characters)), None)
        if shared:
            break
    assert shared is not None, "demo world never schedules a shared event"
    clock.set(shared.start_at + (shared.end_at - shared.start_at) / 2)
    chars = client.get("/api/v1/device/state", headers=auth(token)).json()["characters"]
    assert {c["activity"] for c in chars} == {shared.activity}
    assert len({(c["started_at"], c["ends_at"]) for c in chars}) == 1


def test_two_devices_see_identical_state(client):
    a, b = pair(client), pair(client)
    assert a != b
    ra = client.get("/api/v1/device/state", headers=auth(a))
    rb = client.get("/api/v1/device/state", headers=auth(b))
    assert ra.json() == rb.json()
    assert ra.headers["etag"] == rb.headers["etag"]


def test_state_spans_midnight(client, token, clock):
    """No event crosses midnight in V1; characters fall back to idle and the API keeps working."""
    for hhmm in ("23:59", "00:00", "00:01"):
        h, m = map(int, hhmm.split(":"))
        day = 5 if h == 23 else 6
        clock.set(datetime(2026, 10, day, h, m, tzinfo=TPE))
        r = client.get("/api/v1/device/state", headers=auth(token))
        assert r.status_code == 200
        assert all(c["activity"] == "idle" for c in r.json()["characters"])
