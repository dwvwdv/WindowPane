"""Tuning and new events come from the database, with no code change (Postgres only)."""

from __future__ import annotations

from datetime import datetime

import pytest

from worldpane_server.seed import DEMO_WORLD_ID

from .conftest import TEST_DATABASE_URL, TPE, auth

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="needs WORLDPANE_TEST_DATABASE_URL")


@pytest.fixture
def repo(request):  # override: these tests are about the database only
    from .conftest import _reset_postgres

    pg = request.getfixturevalue("_pg_repo")
    _reset_postgres(pg)
    return pg


def _history(client, token, day: str) -> list[dict]:
    body = client.get("/api/v1/world/history", params={"date": day}, headers=auth(token)).json()
    return [e for c in body["characters"] for e in c["events"]]


def test_new_event_definition_is_pure_data(client, token, repo, clock):
    with repo._pool.connection() as conn:
        conn.execute(
            """with d as (
                 insert into worldpane.event_definitions
                   (key, category, label, scene, location, activity, params, sort_order)
                 values ('cooking', 'leisure', '煮飯', 'home_kitchen', 'HOME', 'cooking',
                         '{"weight": 1000, "min_duration": 20, "max_duration": 40,
                           "allowed_time": [["17:30", "21:00"]],
                           "allowed_context": ["weekday", "holiday", "leave"],
                           "cooldown_min": 1440}', 500)
                 returning id)
               insert into worldpane.profile_event_pools (profile_id, event_definition_id)
               select p.id, d.id from worldpane.character_profiles p, d
                where p.key = 'official.student.v1'"""
        )
    clock.set(datetime(2026, 10, 9, 9, 0, tzinfo=TPE))
    cooking = [e for day in ("2026-10-06", "2026-10-07", "2026-10-08") for e in _history(client, token, day)
               if e["type"] == "cooking"]
    assert cooking, "a definition added only in the DB was never scheduled"
    assert {e["activity"] for e in cooking} == {"cooking"}


def test_tbd_probability_is_tuned_in_db(client, token, repo, clock):
    with repo._pool.connection() as conn:
        conn.execute(
            """update worldpane.character_profiles
                  set meal_config = jsonb_set(meal_config, '{meals,0,skip_probability}', '1')
                where world_id is null"""
        )
    clock.set(datetime(2026, 10, 9, 9, 0, tzinfo=TPE))
    for day in ("2026-10-06", "2026-10-07", "2026-10-08"):
        assert all(e["type"] != "breakfast" for e in _history(client, token, day))


def test_world_override_disables_shared_event(client, token, repo, clock):
    with repo._pool.connection() as conn:
        conn.execute(
            """update worldpane.worlds
                  set shared_event_config = jsonb_set(shared_event_config, '{overrides}',
                      '{"date": {"enabled": false}, "watch_movie": {"enabled": false},
                        "group_dinner": {"enabled": false}, "basketball": {"enabled": false}}')
                where id = %s""",
            (DEMO_WORLD_ID,),
        )
    clock.set(datetime(2026, 10, 20, 9, 0, tzinfo=TPE))
    for d in range(6, 20):
        events = _history(client, token, f"2026-10-{d:02d}")
        assert all(len(e["participants"]) == 1 for e in events)


def test_persisted_plan_is_not_rewritten_by_later_tuning(client, token, repo, clock):
    clock.set(datetime(2026, 10, 7, 9, 0, tzinfo=TPE))
    before = _history(client, token, "2026-10-06")
    with repo._pool.connection() as conn:
        conn.execute("update worldpane.event_definitions set enabled = false")
    assert _history(client, token, "2026-10-06") == before


def test_memory_and_postgres_demo_worlds_match(client, token, settings, clock):
    """The in-memory demo world and supabase/seed.sql describe the same world."""
    from fastapi.testclient import TestClient

    from worldpane_server.main import create_app
    from worldpane_server.repositories.memory import InMemoryRepository

    from .conftest import pair

    mem = TestClient(create_app(settings, repository=InMemoryRepository(), clock=clock))
    mem_token = pair(mem)
    clock.set(datetime(2026, 10, 9, 9, 0, tzinfo=TPE))
    for day in ("2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"):
        assert _history(mem, mem_token, day) == _history(client, token, day)


def test_invalid_override_is_skipped_not_500(client, token, repo, clock):
    with repo._pool.connection() as conn:
        conn.execute(
            """update worldpane.profile_event_pools
                  set overrides = '{"min_duration": 90, "max_duration": 10}'"""
        )
        conn.execute(
            """update worldpane.worlds
                  set shared_event_config = jsonb_set(shared_event_config, '{overrides}',
                      '{"date": {"min_participants": 1}}')"""
        )
    clock.set(datetime(2026, 10, 9, 9, 0, tzinfo=TPE))
    for day in ("2026-10-06", "2026-10-07", "2026-10-08"):
        r = client.get("/api/v1/world/history", params={"date": day}, headers=auth(token))
        assert r.status_code == 200
        types = {e["type"] for c in r.json()["characters"] for e in c["events"]}
        assert "date" not in types and not types & {"slacking", "reading", "shower"}
    assert client.get("/api/v1/world/state", headers=auth(token)).status_code == 200


def test_migrations_only_database_works(settings, clock, request):
    """No seed.sql (e.g. `supabase db push`): startup installs official content as global rows."""
    from fastapi.testclient import TestClient

    from worldpane_server.main import create_app

    from .conftest import _reset_postgres, pair

    pg = request.getfixturevalue("_pg_repo")
    _reset_postgres(pg, seed=False)
    app = TestClient(create_app(settings, repository=pg, clock=clock))
    with pg._pool.connection() as conn:
        owned = conn.execute(
            "select count(*) as n from worldpane.character_profiles where world_id is not null"
        ).fetchone()["n"]
        shared = conn.execute(
            "select count(*) as n from worldpane.event_definitions where category = 'shared' and world_id is null"
        ).fetchone()["n"]
    assert owned == 0 and shared > 0

    created = app.post("/api/v1/world", json={"name": "Our Room"})
    assert created.status_code == 201, created.text
    mine = created.json()["device"]["device_token"]
    assert app.get("/api/v1/world/state", headers=auth(mine)).status_code == 200
    assert app.get("/api/v1/world/state", headers=auth(pair(app))).status_code == 200


def test_world_definition_shadows_official_pool_entry(client, token, repo, clock):
    clock.set(datetime(2026, 10, 9, 9, 0, tzinfo=TPE))
    days = ("2026-10-06", "2026-10-07", "2026-10-08")
    with repo._pool.connection() as conn:
        conn.execute(
            """insert into worldpane.event_definitions
                 (world_id, key, category, label, scene, location, activity, params, enabled, sort_order)
               select %s, key, category, '看漫畫', 'home_bedroom', location, 'reading_comics', params, enabled, sort_order
                 from worldpane.event_definitions where world_id is null and category = 'leisure' and key = 'phone'""",
            (DEMO_WORLD_ID,),
        )
    phones = [e for day in days for e in _history(client, token, day) if e["type"] == "phone"]
    assert phones, "the demo world never scheduled the phone event"
    assert {(e["activity"], e["scene"]) for e in phones} == {("reading_comics", "home_bedroom")}
