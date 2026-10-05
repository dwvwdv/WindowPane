from __future__ import annotations

import hashlib
from datetime import timedelta

from worldpane_server.repositories.memory import InMemoryRepository
from worldpane_server.seed import DEMO_WORLD_ID

from .conftest import DEMO_CODE, auth, pair


def test_pair_happy_path_stores_only_token_hash(client, repo):
    r = client.post("/api/v1/device/pair", json={"pairing_code": DEMO_CODE, "firmware_version": "0.1.0"})
    assert r.status_code == 201
    body = r.json()
    assert body["world_id"] == DEMO_WORLD_ID
    assert body["token_type"] == "Bearer"
    token = body["device_token"]

    devices = repo.list_devices(DEMO_WORLD_ID)
    assert len(devices) == 1
    assert devices[0].device_token_hash == hashlib.sha256(token.encode()).hexdigest()
    if isinstance(repo, InMemoryRepository):
        assert token not in repr(repo.__dict__)  # raw token is never persisted
        assert DEMO_CODE not in repr(repo._codes)  # nor is the raw pairing code
    else:
        with repo._pool.connection() as conn:
            dump = conn.execute(
                "select (select json_agg(d) from worldpane.devices d)::text || "
                "(select json_agg(p) from worldpane.pairing_codes p)::text as t"
            ).fetchone()["t"]
        assert token not in dump and DEMO_CODE not in dump

    assert client.get("/api/v1/world/state", headers=auth(token)).status_code == 200


def test_create_world_then_join_with_code(client):
    r = client.post("/api/v1/world", json={"name": "Our Room"})
    assert r.status_code == 201
    out = r.json()
    world_id, code = out["world_id"], out["pairing"]["pairing_code"]
    assert world_id != DEMO_WORLD_ID
    assert len(code) == 6 and code.isdigit()
    assert world_id not in code
    assert out["pairing"]["max_uses"] == 1

    first = out["device"]["device_token"]
    second = pair(client, code)
    s1 = client.get("/api/v1/world/state", headers=auth(first)).json()
    s2 = client.get("/api/v1/world/state", headers=auth(second)).json()
    assert s1["world_id"] == s2["world_id"] == world_id
    assert s1 == s2


def test_create_world_without_body_and_bad_timezone(client):
    assert client.post("/api/v1/world").status_code == 201
    assert client.post("/api/v1/world", json={"timezone": "Mars/Olympus"}).status_code == 422


def test_expired_code(client, clock, settings):
    code = client.post("/api/v1/world", json={}).json()["pairing"]["pairing_code"]
    clock.advance(timedelta(seconds=settings.pairing_code_ttl_seconds))
    r = client.post("/api/v1/device/pair", json={"pairing_code": code})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "pairing_code_expired"


def test_max_uses_exceeded(client, token):
    r = client.post("/api/v1/world/pairing-codes", headers=auth(token), json={"max_uses": 2})
    assert r.status_code == 201
    code = r.json()["pairing_code"]
    pair(client, code)
    pair(client, code)
    r = client.post("/api/v1/device/pair", json={"pairing_code": code})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "pairing_code_exhausted"


def test_default_code_is_single_use(client):
    code = client.post("/api/v1/world").json()["pairing"]["pairing_code"]
    pair(client, code)
    r = client.post("/api/v1/device/pair", json={"pairing_code": code})
    assert r.json()["detail"]["code"] == "pairing_code_exhausted"


def test_unknown_and_malformed_codes(client):
    unknown = "000000" if DEMO_CODE != "000000" else "999999"
    r = client.post("/api/v1/device/pair", json={"pairing_code": unknown})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_pairing_code"
    for bad in ("12345", "1234567", "abcdef", DEMO_WORLD_ID):
        assert client.post("/api/v1/device/pair", json={"pairing_code": bad}).status_code == 422


def test_device_input_accepted(client, token, repo):
    r = client.post("/api/v1/device/input", headers=auth(token), json={"type": "button_press", "button": "A"})
    assert r.status_code == 202
    assert r.json()["accepted"] is True
    logged = repo.list_device_inputs(DEMO_WORLD_ID)
    assert [(i.type, i.button) for i in logged] == [("button_press", "A")]
    bad = client.post("/api/v1/device/input", headers=auth(token), json={"type": "DROP TABLE"})
    assert bad.status_code == 422
