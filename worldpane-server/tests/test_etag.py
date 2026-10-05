from __future__ import annotations

from datetime import timedelta

from .conftest import auth


def test_etag_304_flow(client, token, clock):
    r1 = client.get("/api/v1/device/state", headers=auth(token))
    etag = r1.headers["etag"]
    assert etag and r1.status_code == 200

    r2 = client.get("/api/v1/device/state", headers={**auth(token), "If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.content == b""
    assert r2.headers["etag"] == etag

    # Weak form and lists are accepted.
    r3 = client.get("/api/v1/device/state", headers={**auth(token), "If-None-Match": f'"x", W/{etag}'})
    assert r3.status_code == 304

    # Polling again a few seconds later with nothing changed: still 304, same revision.
    clock.advance(timedelta(seconds=15))
    r4 = client.get("/api/v1/device/state", headers={**auth(token), "If-None-Match": etag})
    assert r4.status_code == 304


def test_etag_changes_when_state_changes(client, token, clock):
    r1 = client.get("/api/v1/device/state", headers=auth(token))
    ends = min(c["ends_at"] for c in r1.json()["characters"])
    from datetime import datetime

    clock.set(datetime.fromisoformat(ends) + timedelta(seconds=1))
    r2 = client.get("/api/v1/device/state", headers={**auth(token), "If-None-Match": r1.headers["etag"]})
    assert r2.status_code == 200
    assert r2.headers["etag"] != r1.headers["etag"]
    assert r2.json()["revision"] > r1.json()["revision"]


def test_stale_etag_gets_full_body(client, token):
    r = client.get("/api/v1/device/state", headers={**auth(token), "If-None-Match": '"stale.0"'})
    assert r.status_code == 200
    assert r.json()["characters"]
