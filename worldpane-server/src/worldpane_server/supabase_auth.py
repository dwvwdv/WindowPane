"""Verify Supabase Auth access tokens for the dashboard.

The browser signs in against Supabase Auth (GoTrue) directly and sends its access token to
``/api/v1/admin``. The server asks GoTrue who the token belongs to (``GET /auth/v1/user``),
which works with any JWT signing key the project uses and also rejects logged-out sessions.
Accepted tokens are cached for at most ``CACHE_SECONDS`` and never past their own ``exp``, so a
dashboard polling every 15 s does not call GoTrue each time; a logged-out token can therefore
still be accepted for up to ``CACHE_SECONDS``.
Whether that user may use the dashboard is a separate check (``worldpane.admins``).
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

CACHE_SECONDS = 30
CACHE_MAX = 256
TIMEOUT_SECONDS = 5
# Answers that say nothing about the token itself (timeout, rate limit): retry, don't sign out.
TRANSIENT_STATUS = {408, 429}


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str


def _seconds_left(token: str) -> float:
    """Seconds until the JWT's ``exp`` (0 if absent or unreadable). Only bounds the cache of a
    token GoTrue has just accepted, so the payload is read without checking the signature."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return max(0.0, float(claims["exp"]) - time.time())
    except (IndexError, KeyError, TypeError, ValueError):
        return 0.0


class AuthUnavailable(Exception):
    """Supabase Auth could not be reached or answered with a server error."""


class SupabaseAuth:
    def __init__(self, url: str, anon_key: str) -> None:
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, AuthUser]] = {}

    def verify(self, token: str) -> AuthUser | None:
        """The user the access token belongs to, or None if GoTrue rejects it."""
        if token.count(".") != 2:  # not a JWT; don't bother GoTrue
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > now:
                return hit[1]
        user = self._fetch_user(token)
        ttl = min(CACHE_SECONDS, _seconds_left(token)) if user is not None else 0
        if ttl > 0:
            with self._lock:
                if len(self._cache) >= CACHE_MAX:
                    self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
                    if len(self._cache) >= CACHE_MAX:
                        self._cache.clear()
                self._cache[key] = (now + ttl, user)
        return user

    def _fetch_user(self, token: str) -> AuthUser | None:
        req = urllib.request.Request(
            f"{self.url}/auth/v1/user",
            headers={"apikey": self.anon_key, "Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in TRANSIENT_STATUS or exc.code >= 500:
                raise AuthUnavailable(f"Supabase Auth answered HTTP {exc.code}") from exc
            return None  # GoTrue rejected the token: expired, malformed, logged out, unknown user
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise AuthUnavailable(f"Supabase Auth unreachable: {exc}") from exc
        user_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(user_id, str) or not user_id:
            return None
        return AuthUser(id=user_id, email=str(body.get("email") or ""))
