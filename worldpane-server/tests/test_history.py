from __future__ import annotations

from datetime import datetime

import pytest

from .conftest import NOW, auth


def test_history_today_only_past_events(client, token):
    r = client.get("/api/v1/world/history", params={"date": "2026-10-05"}, headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == "2026-10-05" and body["timezone"] == "Asia/Taipei"
    assert [c["appearance"] for c in body["characters"]] == ["xiaobai", "xiaojimao"]
    for c in body["characters"]:
        assert c["events"], "every character has events"
        starts = [datetime.fromisoformat(e["started_at"]) for e in c["events"]]
        assert starts == sorted(starts)
        assert all(s <= NOW for s in starts)
        assert all(s.date().isoformat() == "2026-10-05" for s in starts)
        assert {"school", "work"} & {e["type"] for e in c["events"]}, "weekday base schedule is in history"


def test_history_shared_event_listed_for_every_participant(client, token, clock):
    clock.set(datetime.fromisoformat("2026-10-06T09:00:00+08:00"))
    body = client.get("/api/v1/world/history", params={"date": "2026-10-05"}, headers=auth(token)).json()
    shared = [{e["id"] for e in c["events"] if len(e["participants"]) >= 2} for c in body["characters"]]
    assert shared[0] and all(s == shared[0] for s in shared)


def test_history_is_deterministic(client, token):
    q = {"date": "2026-10-05"}
    a = client.get("/api/v1/world/history", params=q, headers=auth(token)).json()
    b = client.get("/api/v1/world/history", params=q, headers=auth(token)).json()
    assert a == b


def test_history_before_world_start_is_empty(client, token):
    body = client.get("/api/v1/world/history", params={"date": "2026-09-01"}, headers=auth(token)).json()
    assert all(c["events"] == [] for c in body["characters"])


@pytest.mark.parametrize("bad", ["2026-13-01", "2026-02-30", "20261005", "yesterday", ""])
def test_history_rejects_malformed_date(client, token, bad):
    r = client.get("/api/v1/world/history", params={"date": bad}, headers=auth(token))
    assert r.status_code == 422


def test_history_requires_date(client, token):
    assert client.get("/api/v1/world/history", headers=auth(token)).status_code == 422


def test_history_rejects_future_date(client, token):
    r = client.get("/api/v1/world/history", params={"date": "2026-10-06"}, headers=auth(token))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "date_in_future"
