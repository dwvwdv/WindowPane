"""Thread-safe in-memory Repository. Process-local; data is lost on restart."""

from __future__ import annotations

import copy
import threading
import uuid
from collections.abc import Sequence
from datetime import date, datetime

from ..domain import (
    Character,
    CharacterRelationship,
    Device,
    DeviceInput,
    Event,
    PairingCode,
    SORT_ORDER_MAX,
    World,
    WorldSummary,
)
from .base import PairingCodeRejected


class InMemoryRepository:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._worlds: dict[str, World] = {}
        self._characters: dict[str, list[Character]] = {}
        self._relationships: dict[str, list[CharacterRelationship]] = {}
        self._plans: dict[tuple[str, date], list[Event]] = {}
        self._devices: dict[str, Device] = {}
        self._device_by_hash: dict[str, str] = {}
        self._codes: dict[str, PairingCode] = {}
        self._code_by_hash: dict[str, str] = {}
        self._inputs: list[DeviceInput] = []
        self._admins: dict[str, str] = {}

    def install_official_content(self, definitions, profiles) -> None:
        """Nothing to install: in-memory characters carry their profiles directly."""

    # worlds
    def create_world(
        self,
        world: World,
        characters: Sequence[Character] = (),
        relationships: Sequence[CharacterRelationship] = (),
        devices: Sequence[Device] = (),
        pairing_codes: Sequence[PairingCode] = (),
    ) -> None:
        with self._lock:
            # Check everything first so a failure leaves nothing behind.
            if world.id in self._worlds:
                raise ValueError(f"world {world.id} already exists")
            for code in pairing_codes:
                self._check_code_free(code)
            self._worlds[world.id] = copy.deepcopy(world)
            self._characters[world.id] = [copy.deepcopy(c) for c in characters]
            self._relationships[world.id] = [copy.deepcopy(r) for r in relationships]
            try:
                for d in devices:
                    self.add_device(d)
                for code in pairing_codes:
                    self.add_pairing_code(code)
            except BaseException:
                # Roll back, like the Postgres transaction does.
                for d in devices:
                    if self._devices.pop(d.id, None) is not None:
                        self._device_by_hash.pop(d.device_token_hash, None)
                for code in pairing_codes:
                    if self._codes.pop(code.id, None) is not None:
                        self._code_by_hash.pop(code.code_hash, None)
                del self._worlds[world.id], self._characters[world.id], self._relationships[world.id]
                raise

    def get_world(self, world_id: str) -> World | None:
        with self._lock:
            w = self._worlds.get(world_id)
            return copy.deepcopy(w) if w else None

    def list_world_summaries(self) -> list[WorldSummary]:
        with self._lock:
            return [
                WorldSummary(
                    id=w.id, name=w.name, timezone=w.timezone,
                    simulation_start_date=w.simulation_start_date, created_at=w.created_at,
                    revision=w.revision,
                    character_count=sum(c.archived_at is None for c in self._characters[w.id]),
                    device_count=sum(d.world_id == w.id for d in self._devices.values()),
                )
                for w in sorted(self._worlds.values(), key=lambda w: (w.created_at, w.id))
            ]

    def update_world(self, world_id: str, *, name: str | None = None,
                     shared_event_config: dict | None = None) -> None:
        with self._lock:
            w = self._worlds[world_id]
            if name is not None:
                w.name = name
            if shared_event_config is not None:
                w.shared_event_config = copy.deepcopy(shared_event_config)
            w.revision += 1  # like the Postgres worlds_bump_revision trigger

    def bump_world_revision(self, world_id: str) -> int:
        with self._lock:
            w = self._worlds[world_id]
            w.revision += 1
            return w.revision

    def record_state_fingerprint(self, world_id: str, fingerprint: str) -> int:
        with self._lock:
            w = self._worlds[world_id]
            if w.state_fingerprint != fingerprint:
                w.state_fingerprint = fingerprint
                w.revision += 1
            return w.revision

    # characters
    def add_character(self, character: Character, *, relationship_type: str | None = None) -> None:
        with self._lock:
            if character.world_id not in self._worlds:
                raise KeyError(character.world_id)
            existing = self._characters[character.world_id]
            c = copy.deepcopy(character)
            last = max((x.sort_order for x in existing), default=-1)
            if last >= SORT_ORDER_MAX:
                # No room after the last one: renumber 0..n-1 in the current order, then append.
                for i, x in enumerate(sorted(existing, key=lambda x: (x.sort_order, x.id))):
                    x.sort_order = i
                last = len(existing) - 1
            c.sort_order = min(last + 1, SORT_ORDER_MAX)
            if relationship_type:
                self._relationships[c.world_id].extend(
                    CharacterRelationship(id=str(uuid.uuid4()), world_id=c.world_id, character_a_id=x.id,
                                          character_b_id=c.id, relationship_type=relationship_type)
                    for x in existing if x.archived_at is None
                )
            existing.append(c)
            self._worlds[c.world_id].revision += 1  # like characters_bump_revision

    def list_characters(self, world_id: str, include_archived: bool = False) -> list[Character]:
        with self._lock:
            chars = [
                c for c in self._characters.get(world_id, [])
                if include_archived or c.archived_at is None
            ]
            return [copy.deepcopy(c) for c in sorted(chars, key=lambda c: (c.sort_order, c.id))]

    def _character(self, character_id: str) -> Character:
        for chars in self._characters.values():
            for c in chars:
                if c.id == character_id:
                    return c
        raise KeyError(character_id)

    def update_character(self, character_id: str, *, display_name: str | None = None,
                         appearance_key: str | None = None, sort_order: int | None = None) -> None:
        with self._lock:
            c = self._character(character_id)
            if display_name is not None:
                c.display_name = display_name
            if appearance_key is not None:
                c.appearance_key = appearance_key
            if sort_order is not None:
                c.sort_order = sort_order
            self._worlds[c.world_id].revision += 1

    def archive_character(self, character_id: str, at: datetime, *, keep_one_active: bool = False) -> bool:
        with self._lock:
            c = self._character(character_id)
            if c.archived_at is not None:
                return True
            others = [x for x in self._characters[c.world_id] if x.id != c.id and x.archived_at is None]
            if keep_one_active and not others:
                return False
            c.archived_at = at
            self._worlds[c.world_id].revision += 1
            return True

    def add_relationship(self, relationship: CharacterRelationship) -> None:
        with self._lock:
            self._relationships[relationship.world_id].append(copy.deepcopy(relationship))

    def list_relationships(self, world_id: str) -> list[CharacterRelationship]:
        with self._lock:
            return copy.deepcopy(self._relationships.get(world_id, []))

    # events
    def get_daily_plan(self, world_id: str, local_date: date) -> list[Event] | None:
        with self._lock:
            plan = self._plans.get((world_id, local_date))
            return copy.deepcopy(plan) if plan is not None else None

    def save_daily_plan(self, world_id: str, local_date: date, events: list[Event]) -> bool:
        with self._lock:
            key = (world_id, local_date)
            if key in self._plans:
                return False
            self._plans[key] = copy.deepcopy(events)
            return True

    # devices
    def add_device(self, device: Device) -> None:
        with self._lock:
            self._devices[device.id] = copy.deepcopy(device)
            self._device_by_hash[device.device_token_hash] = device.id

    def get_device_by_token_hash(self, token_hash: str) -> Device | None:
        with self._lock:
            device_id = self._device_by_hash.get(token_hash)
            return copy.deepcopy(self._devices[device_id]) if device_id else None

    def touch_device(self, device_id: str, seen_at: datetime) -> None:
        with self._lock:
            if device_id in self._devices:
                self._devices[device_id].last_seen_at = seen_at

    def list_devices(self, world_id: str) -> list[Device]:
        with self._lock:
            return [copy.deepcopy(d) for d in self._devices.values() if d.world_id == world_id]

    # pairing codes
    def _check_code_free(self, code: PairingCode) -> None:
        existing_id = self._code_by_hash.get(code.code_hash)
        if existing_id is not None:
            existing = self._codes[existing_id]
            if not existing.is_expired(code.created_at) and not existing.is_exhausted():
                raise ValueError("an active pairing code with this value already exists")

    def add_pairing_code(self, code: PairingCode) -> None:
        with self._lock:
            self._check_code_free(code)
            self._codes[code.id] = copy.deepcopy(code)
            self._code_by_hash[code.code_hash] = code.id

    def get_pairing_code_by_hash(self, code_hash: str) -> PairingCode | None:
        with self._lock:
            code_id = self._code_by_hash.get(code_hash)
            return copy.deepcopy(self._codes[code_id]) if code_id else None

    def redeem_pairing_code(self, code_id: str, device: Device, now: datetime) -> PairingCode:
        with self._lock:
            code = self._codes[code_id]
            if code.is_expired(now):
                raise PairingCodeRejected("expired")
            if code.is_exhausted():
                raise PairingCodeRejected("exhausted")
            self.add_device(device)
            code.used_count += 1
            return copy.deepcopy(code)

    # device input
    def add_device_input(self, item: DeviceInput) -> None:
        with self._lock:
            self._inputs.append(copy.deepcopy(item))

    def get_admin_name(self, user_id: str) -> str | None:
        with self._lock:
            return self._admins.get(user_id)

    def add_admin(self, user_id: str, display_name: str) -> None:
        """Not part of the Protocol (Postgres admins are rows in worldpane.admins); for tests/dev."""
        with self._lock:
            self._admins[user_id] = display_name

    def list_device_inputs(self, world_id: str) -> list[DeviceInput]:
        """Not part of the Protocol; handy for tests/debugging."""
        with self._lock:
            return [copy.deepcopy(i) for i in self._inputs if i.world_id == world_id]
