"""Runtime settings, read from environment variables (prefix ``WORLDPANE_``) or a ``.env`` file.

No secrets live in the repository. In ``dev`` an ephemeral pairing-code secret is generated
at startup if none is configured; any other environment refuses to start without one.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORLDPANE_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"

    # HMAC key used to hash pairing codes. A 6-digit code has only 10^6 values, so a plain
    # sha256 would be trivially reversible from a DB dump; an HMAC with a server-side key is not.
    pairing_code_secret: str = ""
    pairing_code_ttl_seconds: int = Field(default=600, ge=30, le=7 * 24 * 3600)
    pairing_code_max_uses: int = Field(default=1, ge=1, le=20)

    default_timezone: str = "Asia/Taipei"

    seed_demo_world: bool = True
    # Dev convenience: a fixed pairing code for the seeded demo world. Random when empty.
    demo_pairing_code: str = ""

    repository: Literal["memory", "postgres"] = "memory"
    simulation_provider: Literal["core"] = "core"

    # Postgres DSN (Supabase: the service-role connection string). Never commit a value.
    database_url: str = ""

    # Dashboard sign-in with Supabase Auth: the project URL and its anon (publishable) key. Both
    # are public values the browser needs anyway; accounts also need a row in worldpane.admins.
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # Optional shared Bearer token for the admin API (scripts, CI, a dashboard without Supabase).
    # The admin API is disabled when neither this nor Supabase Auth is configured.
    admin_token: str = ""

    @model_validator(mode="after")
    def _ensure_secret(self) -> "Settings":
        if not self.pairing_code_secret:
            if self.env == "prod":
                raise ValueError("WORLDPANE_PAIRING_CODE_SECRET must be set when WORLDPANE_ENV=prod")
            self.pairing_code_secret = secrets.token_urlsafe(32)
        if self.demo_pairing_code and not (
            len(self.demo_pairing_code) == 6 and self.demo_pairing_code.isdigit()
        ):
            raise ValueError("WORLDPANE_DEMO_PAIRING_CODE must be 6 digits")
        if self.admin_token and len(self.admin_token) < 16:
            raise ValueError("WORLDPANE_ADMIN_TOKEN must be at least 16 characters")
        if bool(self.supabase_url) != bool(self.supabase_anon_key):
            raise ValueError("Set both WORLDPANE_SUPABASE_URL and WORLDPANE_SUPABASE_ANON_KEY, or neither")
        if self.supabase_url and not self.supabase_url.startswith(("https://", "http://")):
            raise ValueError("WORLDPANE_SUPABASE_URL must be an http(s) URL")
        self.supabase_url = self.supabase_url.rstrip("/")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
