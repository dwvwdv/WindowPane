"""Admin API behind /dashboard: auth, create / adjust Worlds, monitor wall."""

from __future__ import annotations

import threading
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from worldpane_server.config import Settings
from worldpane_server.main import create_app
from worldpane_server.repositories.memory import InMemoryRepository
from worldpane_server.seed import DEMO_CHARACTER_IDS, DEMO_WORLD_ID

from .conftest import DEMO_CODE, TPE, auth, pair

ADMIN_TOKEN = "admin-token-for-tests-0123"
A = "/api/v1/admin"
ADMIN = auth(ADMIN_TOKEN)
TRIO = [
    {"display_name": "小白", "appearance": "xiaobai", "profile_key": "official.student.v1"},
    {"display_name": "小雞毛", "appearance": "xiaojimao", "profile_key": "official.office_worker.v1"},
    {"display_name": "阿毛", "appearance": "amao", "profile_key": "official.freelancer.v1"},
]


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", pairing_code_secret="test-secret", seed_demo_world=True,
                    demo_pairing_code=DEMO_CODE, admin_token=ADMIN_TOKEN)


def _create(client: TestClient, **body) -> dict:
    r = client.post(f"{A}/worlds", json=body, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()


# --- auth ------------------------------------------------------------------------------
def test_admin_requires_the_admin_token(client, token):
    assert client.get(f"{A}/worlds").status_code == 401
    assert client.get(f"{A}/worlds", headers=auth("x" * 26)).status_code == 401
    # A device token is not an admin token.
    assert client.get(f"{A}/worlds", headers=auth(token)).status_code == 401
    assert client.get(f"{A}/worlds", headers=ADMIN).status_code == 200


def test_admin_is_disabled_without_a_token(repo, clock):
    app = create_app(Settings(env="test", pairing_code_secret="s", seed_demo_world=False),
                     repository=repo, clock=clock)
    r = TestClient(app).get(f"{A}/worlds", headers=ADMIN)
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "admin_disabled"


def test_short_admin_token_is_rejected():
    with pytest.raises(ValueError):
        Settings(env="test", admin_token="short")


def test_dashboard_page_is_served_and_admin_routes_stay_out_of_openapi(client):
    r = client.get("/dashboard")
    assert r.status_code == 200 and "窗間 Dashboard" in r.text
    paths = client.get("/openapi.json").json()["paths"]
    assert "/dashboard" not in paths
    assert not [p for p in paths if p.startswith(A)]


# --- worlds ----------------------------------------------------------------------------
def test_list_and_read_the_demo_world(client):
    worlds = client.get(f"{A}/worlds", headers=ADMIN).json()
    demo = next(w for w in worlds if w["id"] == DEMO_WORLD_ID)
    assert demo["character_count"] == 2 and demo["timezone"] == "Asia/Taipei"

    w = client.get(f"{A}/worlds/{DEMO_WORLD_ID}", headers=ADMIN).json()
    assert [c["display_name"] for c in w["characters"]] == ["小白", "小雞毛"]
    assert {e["key"] for e in w["shared_events"]} >= {"watch_movie", "date"}
    assert client.get(f"{A}/worlds/not-a-uuid", headers=ADMIN).status_code == 422
    r = client.get(f"{A}/worlds/00000000-0000-4000-a000-0000000000ff", headers=ADMIN)
    assert r.status_code == 404


def test_create_world_with_custom_characters_and_pair_a_device(client):
    out = _create(client, name="三人宿舍", timezone="Asia/Tokyo", pairing_max_uses=2, characters=TRIO)
    world = out["world"]
    assert world["timezone"] == "Asia/Tokyo" and world["devices"] == []
    assert [c["display_name"] for c in world["characters"]] == ["小白", "小雞毛", "阿毛"]
    assert out["pairing"]["max_uses"] == 2

    token = pair(client, out["pairing"]["pairing_code"])
    state = client.get("/api/v1/world/state", headers=auth(token)).json()
    assert state["world_id"] == world["id"]
    assert [c["appearance"] for c in state["characters"]] == ["xiaobai", "xiaojimao", "amao"]

    summary = next(w for w in client.get(f"{A}/worlds", headers=ADMIN).json() if w["id"] == world["id"])
    assert summary["character_count"] == 3 and summary["device_count"] == 1


def test_create_world_defaults_and_validation(client):
    out = _create(client)
    assert [c["appearance"] for c in out["world"]["characters"]] == ["xiaobai", "xiaojimao"]
    bad = client.post(f"{A}/worlds", headers=ADMIN, json={"characters": [
        {"display_name": "X", "appearance": "x", "profile_key": "nope"}]})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "unknown_profile"
    assert client.post(f"{A}/worlds", headers=ADMIN, json={"characters": []}).status_code == 422
    assert client.post(f"{A}/worlds", headers=ADMIN, json={"timezone": "Mars/Base"}).status_code == 422
    assert client.post(f"{A}/worlds", headers=ADMIN, json={"name": "  "}).status_code == 422


def test_rename_and_tune_shared_events(client):
    cfg = {"attempts": 3, "trigger_probability": 0.8, "overrides": {"date": {"enabled": False}}}
    r = client.patch(f"{A}/worlds/{DEMO_WORLD_ID}", headers=ADMIN,
                     json={"name": "新名字", "shared_event_config": cfg})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "新名字"
    assert r.json()["shared_event_config"] == cfg
    assert client.get(f"{A}/worlds/{DEMO_WORLD_ID}", headers=ADMIN).json()["shared_event_config"] == cfg


@pytest.mark.parametrize("cfg, fragment", [
    ({"attempts": -1}, "attempts"),
    ({"trigger_probability": 2}, "trigger_probability"),
    ({"bogus": 1}, "unknown key: bogus"),
    ({"overrides": {"nope": {}}}, "overrides.nope"),
    ({"overrides": {"date": {"weight": "high"}}}, "date"),
    ({"overrides": []}, "overrides"),
    ({"overrides": {"date": {"enabled": "false"}}}, "overrides.date.enabled"),
    ({"overrides": {"date": {"context_overrides": {"holiday": {"enabled": 0}}}}},
     "overrides.date.context_overrides.holiday.enabled"),
    ({"overrides": {"date": {"context_overrides": []}}}, "overrides.date.context_overrides"),
])
def test_invalid_shared_config_is_a_422_and_not_stored(client, cfg, fragment):
    before = client.get(f"{A}/worlds/{DEMO_WORLD_ID}", headers=ADMIN).json()["shared_event_config"]
    r = client.patch(f"{A}/worlds/{DEMO_WORLD_ID}", headers=ADMIN, json={"shared_event_config": cfg})
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "invalid_shared_event_config"
    assert fragment in r.json()["detail"]["message"]
    after = client.get(f"{A}/worlds/{DEMO_WORLD_ID}", headers=ADMIN).json()["shared_event_config"]
    assert after == before


def test_disabled_shared_event_stays_out_of_new_plans(client, clock):
    off = {name: {"enabled": False} for name in ("watch_movie", "date", "group_dinner", "basketball")}
    r = client.patch(f"{A}/worlds/{DEMO_WORLD_ID}", headers=ADMIN,
                     json={"shared_event_config": {"attempts": 5, "trigger_probability": 1, "overrides": off}})
    assert r.status_code == 200, r.text
    clock.set(datetime(2026, 10, 11, 23, 0, tzinfo=TPE))  # a holiday not planned yet
    h = client.get(f"{A}/worlds/{DEMO_WORLD_ID}/history", headers=ADMIN, params={"date": "2026-10-11"}).json()
    assert all(len(e["participants"]) == 1 for c in h["characters"] for e in c["events"])


# --- characters ------------------------------------------------------------------------
def test_add_rename_and_archive_characters(client, token):
    w = client.post(f"{A}/worlds/{DEMO_WORLD_ID}/characters", headers=ADMIN, json={
        "display_name": " 小橘 ", "appearance": "xiaoju", "profile_key": "official.freelancer.v1"})
    assert w.status_code == 201, w.text
    new = w.json()["characters"][-1]
    assert new["display_name"] == "小橘" and new["sort_order"] == 2
    state = client.get("/api/v1/world/state", headers=auth(token)).json()
    assert [c["id"] for c in state["characters"]][-1] == new["id"]

    r = client.patch(f"{A}/worlds/{DEMO_WORLD_ID}/characters/{new['id']}", headers=ADMIN,
                     json={"appearance": "orange", "sort_order": -1})
    assert r.status_code == 200
    after = client.get("/api/v1/world/state", headers=auth(token)).json()
    assert after["characters"][0]["appearance"] == "orange"  # moved to the front
    assert after["revision"] > state["revision"]

    r = client.delete(f"{A}/worlds/{DEMO_WORLD_ID}/characters/{DEMO_CHARACTER_IDS[1]}", headers=ADMIN)
    assert r.status_code == 200
    archived = [c for c in r.json()["characters"] if c["archived_at"]]
    assert [c["id"] for c in archived] == [DEMO_CHARACTER_IDS[1]]
    ids = [c["id"] for c in client.get("/api/v1/world/state", headers=auth(token)).json()["characters"]]
    assert DEMO_CHARACTER_IDS[1] not in ids


def test_cannot_archive_the_last_character_or_touch_another_worlds(client):
    other = _create(client)["world"]
    r = client.delete(f"{A}/worlds/{DEMO_WORLD_ID}/characters/{DEMO_CHARACTER_IDS[0]}", headers=ADMIN)
    assert r.status_code == 200
    r = client.delete(f"{A}/worlds/{DEMO_WORLD_ID}/characters/{DEMO_CHARACTER_IDS[1]}", headers=ADMIN)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "last_character"

    foreign = other["characters"][0]["id"]
    r = client.patch(f"{A}/worlds/{DEMO_WORLD_ID}/characters/{foreign}", headers=ADMIN, json={"display_name": "x"})
    assert r.status_code == 404
    assert client.post(f"{A}/worlds/{DEMO_WORLD_ID}/characters", headers=ADMIN, json={
        "display_name": "X", "appearance": "Bad Key", "profile_key": "official.student.v1"}).status_code == 422


def test_new_character_gets_relationships_with_active_characters(client, repo):
    w = client.post(f"{A}/worlds/{DEMO_WORLD_ID}/characters", headers=ADMIN, json={
        "display_name": "小橘", "appearance": "xiaoju", "profile_key": "official.freelancer.v1"}).json()
    new = w["characters"][-1]["id"]
    pairs = {frozenset((r.character_a_id, r.character_b_id)) for r in repo.list_relationships(DEMO_WORLD_ID)}
    assert {frozenset((new, cid)) for cid in DEMO_CHARACTER_IDS} <= pairs


def test_failed_relationship_insert_leaves_no_character(client, repo, monkeypatch):
    if isinstance(repo, InMemoryRepository):
        pytest.skip("in-memory inserts cannot fail half-way")

    def boom(*_args, **_kwargs):
        raise RuntimeError("relationship insert failed")

    monkeypatch.setattr(type(repo), "_insert_relationship", staticmethod(boom))
    with pytest.raises(RuntimeError):
        client.post(f"{A}/worlds/{DEMO_WORLD_ID}/characters", headers=ADMIN, json={
            "display_name": "小橘", "appearance": "xiaoju", "profile_key": "official.freelancer.v1"})
    names = [c.display_name for c in repo.list_characters(DEMO_WORLD_ID, include_archived=True)]
    assert names == ["小白", "小雞毛"]


def test_concurrent_archives_keep_one_active_character(client, repo, clock):
    for _ in range(5):
        chars = [c["id"] for c in _create(client)["world"]["characters"]]
        barrier = threading.Barrier(len(chars))
        results: list[bool] = []

        def archive(cid: str) -> None:
            barrier.wait()
            results.append(repo.archive_character(cid, clock.now(), keep_one_active=True))

        threads = [threading.Thread(target=archive, args=(cid,)) for cid in chars]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(results) == [False, True]


# --- pairing, history, monitor ---------------------------------------------------------
def test_issue_pairing_code_and_read_history(client):
    code = client.post(f"{A}/worlds/{DEMO_WORLD_ID}/pairing-codes", headers=ADMIN, json={"max_uses": 3})
    assert code.status_code == 201
    assert pair(client, code.json()["pairing_code"])
    h = client.get(f"{A}/worlds/{DEMO_WORLD_ID}/history", headers=ADMIN, params={"date": "2026-10-05"})
    assert h.status_code == 200 and h.json()["characters"][0]["events"]
    future = client.get(f"{A}/worlds/{DEMO_WORLD_ID}/history", headers=ADMIN, params={"date": "2026-12-01"})
    assert future.status_code == 422


def test_monitor_shows_many_worlds_at_once(client):
    trio = _create(client, name="三人宿舍", characters=TRIO)["world"]
    wall = client.get(f"{A}/monitor", headers=ADMIN).json()["worlds"]
    assert {w["world_id"] for w in wall} == {DEMO_WORLD_ID, trio["id"]}
    tile = next(w for w in wall if w["world_id"] == trio["id"])
    assert [c["display_name"] for c in tile["characters"]] == ["小白", "小雞毛", "阿毛"]
    assert all(c["scene"] and c["activity"] for c in tile["characters"])

    only = client.get(f"{A}/monitor", headers=ADMIN, params={"world_id": [trio["id"]]}).json()["worlds"]
    assert [w["world_id"] for w in only] == [trio["id"]]
    missing = "00000000-0000-4000-a000-0000000000ff"
    assert client.get(f"{A}/monitor", headers=ADMIN, params={"world_id": [missing]}).json() == {"worlds": []}
    assert client.get(f"{A}/monitor", headers=ADMIN, params={"world_id": ["nope"]}).status_code == 422


def test_monitor_matches_what_devices_see(client):
    token = pair(client, DEMO_CODE)
    device = client.get("/api/v1/world/state", headers=auth(token)).json()
    tile = client.get(f"{A}/monitor", headers=ADMIN, params={"world_id": [DEMO_WORLD_ID]}).json()["worlds"][0]
    assert tile["revision"] == device["revision"]
    assert [{k: c[k] for k in ("id", "scene", "activity")} for c in tile["characters"]] == \
           [{k: c[k] for k in ("id", "scene", "activity")} for c in device["characters"]]
