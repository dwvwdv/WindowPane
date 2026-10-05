"""Persistence seam.

The API/service layer depends only on this Protocol. Implementations:

* ``InMemoryRepository`` (``repositories/memory.py``) — used now, for dev and tests.
* ``PostgresRepository`` (``repositories/postgres.py``) — TODO, will target the Supabase
  schema being built under ``/supabase``.

Methods are synchronous; FastAPI runs ``def`` endpoints in a threadpool. If the Postgres
implementation ends up async, switch this Protocol and the service layer together.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from ..domain import (
    Character,
    CharacterRelationship,
    Device,
    DeviceInput,
    Event,
    PairingCode,
    World,
)


class PairingCodeRejected(Exception):
    """Raised by ``consume_pairing_code`` when the code can no longer be used."""

    def __init__(self, reason: str) -> None:  # "expired" | "exhausted"
        super().__init__(reason)
        self.reason = reason


@runtime_checkable
class Repository(Protocol):
    # --- worlds -----------------------------------------------------------------------
    def create_world(self, world: World) -> None: ...

    def get_world(self, world_id: str) -> World | None: ...

    def bump_world_revision(self, world_id: str) -> int:
        """Atomically increment and return ``worlds.revision``."""
        ...

    def record_state_fingerprint(self, world_id: str, fingerprint: str) -> int:
        """If ``fingerprint`` differs from the stored one, store it and bump ``revision``.
        Returns the (possibly new) revision. Must be atomic: in Postgres,
        ``UPDATE worlds SET revision = revision + 1, state_fingerprint = $2
        WHERE id = $1 AND state_fingerprint IS DISTINCT FROM $2`` then read revision."""
        ...

    # --- characters / relationships ------------------------------------------------------
    def add_character(self, character: Character) -> None: ...

    def list_characters(self, world_id: str) -> list[Character]:
        """All characters of a World (1..N), in stable display order."""
        ...

    def add_relationship(self, relationship: CharacterRelationship) -> None: ...

    def list_relationships(self, world_id: str) -> list[CharacterRelationship]: ...

    # --- events ------------------------------------------------------------------------
    def get_daily_plan(self, world_id: str, local_date: date) -> list[Event] | None:
        """Persisted events for that World-local date, or ``None`` if never generated."""
        ...

    def save_daily_plan(self, world_id: str, local_date: date, events: list[Event]) -> bool:
        """Persist a generated plan. Returns False (and stores nothing) if a plan for that
        date already exists — generation is deterministic, so the first writer wins."""
        ...

    # --- devices -----------------------------------------------------------------------
    def add_device(self, device: Device) -> None: ...

    def get_device_by_token_hash(self, token_hash: str) -> Device | None: ...

    def touch_device(self, device_id: str, seen_at: datetime) -> None: ...

    def list_devices(self, world_id: str) -> list[Device]: ...

    # --- pairing codes ---------------------------------------------------------------------
    def add_pairing_code(self, code: PairingCode) -> None:
        """Raises ValueError if an *active* code with the same hash already exists."""
        ...

    def get_pairing_code_by_hash(self, code_hash: str) -> PairingCode | None: ...

    def consume_pairing_code(self, code_id: str, now: datetime) -> PairingCode:
        """Atomically check expiry/max_uses and increment ``used_count``.

        Raises ``PairingCodeRejected``. In Postgres this is a single
        ``UPDATE ... SET used_count = used_count + 1 WHERE id = $1 AND expires_at > now()
        AND used_count < max_uses RETURNING *``.
        """
        ...

    # --- device input ------------------------------------------------------------------
    def add_device_input(self, item: DeviceInput) -> None: ...
