"""Dashboard sign-in with Supabase Auth: token verification, the worldpane.admins allow-list,
and the shared admin token as a fallback."""

from __future__ import annotations

import io
import json
import re
import urllib.error

import pytest
from fastapi.testclient import TestClient

from worldpane_server import supabase_auth
from worldpane_server.config import Settings
from worldpane_server.main import create_app
from worldpane_server.repositories.memory import InMemoryRepository
from worldpane_server.supabase_auth import AuthUnavailable, AuthUser, SupabaseAuth

from .conftest import auth

A = "/api/v1/admin"
SB_URL = "https://example.supabase.co"
ADMIN_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ID = "22222222-2222-4222-8222-222222222222"
ADMIN_JWT = "header.admin.sig"
OTHER_JWT = "header.other.sig"
ADMIN_TOKEN = "shared-admin-token-0123"


class FakeVerifier:
    """Stands in for SupabaseAuth: maps access tokens to users."""

    def __init__(self) -> None:
        self.users = {ADMIN_JWT: AuthUser(ADMIN_ID, "admin@example.com"),
                      OTHER_JWT: AuthUser(OTHER_ID, "other@example.com")}
        self.down = False

    def verify(self, token: str) -> AuthUser | None:
        if self.down:
            raise AuthUnavailable("down")
        return self.users.get(token)


def _add_admin(repo, user_id: str, name: str) -> None:
    if isinstance(repo, InMemoryRepository):
        repo.add_admin(user_id, name)
    else:
        with repo._pool.connection() as conn:
            conn.execute("insert into worldpane.admins (user_id, display_name) values (%s, %s)", (user_id, name))


@pytest.fixture
def verifier() -> FakeVerifier:
    return FakeVerifier()


def _app(repo, clock, verifier, **settings):
    base = dict(env="test", pairing_code_secret="s", seed_demo_world=False,
                supabase_url=SB_URL, supabase_anon_key="anon-key")
    base.update(settings)
    return TestClient(create_app(Settings(**base), repository=repo, clock=clock, auth_verifier=verifier))


def test_listed_supabase_user_can_use_the_admin_api(repo, clock, verifier):
    _add_admin(repo, ADMIN_ID, "阿管")
    client = _app(repo, clock, verifier)
    me = client.get(f"{A}/me", headers=auth(ADMIN_JWT))
    assert me.status_code == 200
    assert me.json() == {"via": "supabase", "user_id": ADMIN_ID, "email": "admin@example.com",
                         "display_name": "阿管"}
    assert client.get(f"{A}/worlds", headers=auth(ADMIN_JWT)).status_code == 200


def test_signed_in_but_not_listed_is_forbidden(repo, clock, verifier):
    _add_admin(repo, ADMIN_ID, "阿管")
    r = _app(repo, clock, verifier).get(f"{A}/worlds", headers=auth(OTHER_JWT))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_admin"


def test_invalid_or_missing_session_is_unauthorized(repo, clock, verifier):
    client = _app(repo, clock, verifier)
    assert client.get(f"{A}/worlds").status_code == 401
    r = client.get(f"{A}/worlds", headers=auth("header.unknown.sig"))
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_supabase_outage_is_a_503_not_a_logout(repo, clock, verifier):
    _add_admin(repo, ADMIN_ID, "阿管")
    verifier.down = True
    r = _app(repo, clock, verifier).get(f"{A}/worlds", headers=auth(ADMIN_JWT))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "auth_unavailable"


def test_shared_token_still_works_next_to_supabase(repo, clock, verifier):
    client = _app(repo, clock, verifier, admin_token=ADMIN_TOKEN)
    me = client.get(f"{A}/me", headers=auth(ADMIN_TOKEN))
    assert me.status_code == 200 and me.json()["via"] == "token"
    # Without admin_token configured the same value is just an unknown session.
    assert _app(repo, clock, verifier).get(f"{A}/me", headers=auth(ADMIN_TOKEN)).status_code == 401


def test_admin_api_disabled_without_any_sign_in_method(repo, clock):
    client = TestClient(create_app(Settings(env="test", pairing_code_secret="s", seed_demo_world=False),
                                   repository=repo, clock=clock))
    r = client.get(f"{A}/me", headers=auth(ADMIN_JWT))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "admin_disabled"


def test_dashboard_page_embeds_public_sign_in_config(repo, clock, verifier):
    page = _app(repo, clock, verifier).get("/dashboard").text
    config = json.loads(re.search(r"const CONFIG = (\{.*?\}) \|\|", page).group(1))
    assert config == {"supabase_url": SB_URL, "supabase_anon_key": "anon-key", "token_login": False}
    page = _app(repo, clock, verifier, admin_token=ADMIN_TOKEN).get("/dashboard").text
    assert '"token_login":true' in page


def test_supabase_settings_come_in_pairs():
    with pytest.raises(ValueError):
        Settings(env="test", supabase_url=SB_URL)
    with pytest.raises(ValueError):
        Settings(env="test", supabase_url="ftp://x", supabase_anon_key="k")
    assert Settings(env="test", supabase_url=SB_URL + "/", supabase_anon_key="k").supabase_url == SB_URL


# --- SupabaseAuth against a stubbed GoTrue ----------------------------------------------
class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _gotrue(monkeypatch, handler):
    calls = []

    def urlopen(req, timeout):
        calls.append((req.full_url, dict(req.header_items())))
        return handler(req)

    monkeypatch.setattr(supabase_auth.urllib.request, "urlopen", urlopen)
    return calls


def test_verify_asks_gotrue_and_caches(monkeypatch):
    calls = _gotrue(monkeypatch, lambda req: _Resp(json.dumps({"id": ADMIN_ID, "email": "a@x"}).encode()))
    sb = SupabaseAuth(SB_URL + "/", "anon-key")
    assert sb.verify(ADMIN_JWT) == AuthUser(ADMIN_ID, "a@x")
    assert sb.verify(ADMIN_JWT) == AuthUser(ADMIN_ID, "a@x")
    assert len(calls) == 1
    url, headers = calls[0]
    assert url == f"{SB_URL}/auth/v1/user"
    assert headers["Apikey"] == "anon-key" and headers["Authorization"] == f"Bearer {ADMIN_JWT}"


def test_verify_rejects_without_caching(monkeypatch):
    def deny(req):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"{}"))

    calls = _gotrue(monkeypatch, deny)
    sb = SupabaseAuth(SB_URL, "anon-key")
    assert sb.verify(ADMIN_JWT) is None
    assert sb.verify(ADMIN_JWT) is None
    assert len(calls) == 2
    assert sb.verify("not-a-jwt") is None and len(calls) == 2  # never sent to GoTrue


@pytest.mark.parametrize("error", [
    urllib.error.HTTPError(SB_URL, 502, "Bad Gateway", {}, io.BytesIO(b"")),
    urllib.error.URLError("connection refused"),
    TimeoutError("timed out"),
])
def test_verify_reports_outages(monkeypatch, error):
    def boom(req):
        raise error

    _gotrue(monkeypatch, boom)
    with pytest.raises(AuthUnavailable):
        SupabaseAuth(SB_URL, "anon-key").verify(ADMIN_JWT)
