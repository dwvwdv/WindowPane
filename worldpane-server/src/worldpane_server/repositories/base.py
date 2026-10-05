"""Persistence seam.

The API/service layer depends only on this Protocol. Implementations:

* ``InMemoryRepository`` (``repositories/memory.py``) — dev and tests.
* ``PostgresRepository`` (``repositories/postgres.py``) — the Supabase schema under ``/supabase``.

Methods are synchronous; FastAPI runs ``def`` endpoints in a threadpool.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from worldpane_core.catalog import EventDefinition

from ..domain import (
    Character,
    CharacterProfile,
    CharacterRelationship,
    Device,
    DeviceInput,
    Event,
    PairingCode,
    World,
)


class PairingCodeRejected(Exception):
    """Raised by ``redeem_pairing_code`` when the code can no longer be used."""

    def __init__(self, reason: str) -> None:  # "expired" | "exhausted"
        super().__init__(reason)
        self.reason = reason


@runtime_checkable
class Repository(Protocol):
    # --- official content ---------------------------------------------------------------
    def install_official_content(
        self, definitions: list[EventDefinition], profiles: list[CharacterProfile]
    ) -> None:
        """Make sure the official event catalog and profile templates exist as GLOBAL rows
        (``world_id`` NULL), so a migration-only database works without ``seed.sql``.
        Existing rows are left untouched: tuning done in the database is never overwritten."""
        ...

    # --- worlds -----------------------------------------------------------------------
    def create_world(
        self,
        world: World,
        characters: Sequence[Character] = (),
        relationships: Sequence[CharacterRelationship] = (),
        devices: Sequence[Device] = (),
        pairing_codes: Sequence[PairingCode] = (),
    ) -> None:
        """Create ``world`` with its initial characters, relationships, devices and pairing codes
        all-or-nothing: on any failure (e.g. ``ValueError`` for a pairing-code collision) nothing
        is left behind, so a retry never leaves partial or orphaned worlds."""
        ...

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

    def list_characters(self, world_id: str, include_archived: bool = False) -> list[Character]:
        """Characters of a World (1..N), in stable display order.

        Archived (soft-deleted) characters are excluded unless ``include_archived``: they no
        longer get new plans, but their history must stay readable."""
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

    def redeem_pairing_code(self, code_id: str, device: Device, now: datetime) -> PairingCode:
        """Atomically check expiry/max_uses, increment ``used_count`` AND insert ``device``.

        Both happen in one transaction, so a crash or a failed device insert never burns a
        single-use code without handing out credentials. Raises ``PairingCodeRejected``.
        """
        ...

    # --- device input ------------------------------------------------------------------
    def add_device_input(self, item: DeviceInput) -> None: ...
