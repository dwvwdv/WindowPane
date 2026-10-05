from __future__ import annotations

import pytest

PROTECTED = [
    ("get", "/api/v1/device/state", None),
    ("get", "/api/v1/world/history?date=2026-10-05", None),
    ("post", "/api/v1/device/input", {"type": "button_press", "button": "A"}),
    ("post", "/api/v1/world/pairing-codes", {}),
]


@pytest.mark.parametrize("method,path,body", PROTECTED)
@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wpd_not-a-real-token"}, {"Authorization": "Basic Zm9vOmJhcg=="}],
)
def test_auth_required(client, method, path, body, headers):
    r = getattr(client, method)(path, headers=headers, **({"json": body} if body is not None else {}))
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.json()["detail"]["code"] == "unauthorized"
