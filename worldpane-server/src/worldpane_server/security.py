"""Token / pairing-code generation and hashing.

* Device tokens: 256-bit random, returned to the device exactly once; only sha256 is stored.
* Pairing codes: 6 random digits, stored as HMAC-SHA256(secret, code). The code carries no
  information about the World (spec §22: 不直接暴露 World ID).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

DEVICE_TOKEN_PREFIX = "wpd_"


def new_id() -> str:
    """Random UUID string; every id is a uuid column in the database."""
    return str(uuid.uuid4())


def generate_device_token() -> str:
    return DEVICE_TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_pairing_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_pairing_code(code: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), code.encode("utf-8"), hashlib.sha256).hexdigest()
