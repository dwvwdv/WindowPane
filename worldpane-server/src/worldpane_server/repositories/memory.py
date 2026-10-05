"""Thread-safe in-memory Repository. Process-local; data is lost on restart."""

from __future__ import annotations

import copy
import threading
from datetime import date, datetime

from ..domain import (
    Character,
    CharacterRelationship,
    Device,
    DeviceInput,
    Event,
    PairingCode,
    World,
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

    # worlds
    def create_world(self, world: World) -> None:
        with self._lock:
            if world.id in self._worlds:
                raise ValueError(f"world {world.id} already exists")
            self._worlds[world.id] = copy.deepcopy(world)
            self._characters.setdefault(world.id, [])
            self._relationships.setdefault(world.id, [])

    def get_world(self, world_id: str) -> World | None:
        with self._lock:
            w = self._worlds.get(world_id)
            return copy.deepcopy(w) if w else None

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
    def add_character(self, character: Character) -> None:
        with self._lock:
            if character.world_id not in self._worlds:
                raise KeyError(character.world_id)
            self._characters[character.world_id].append(copy.deepcopy(character))

    def list_characters(self, world_id: str) -> list[Character]:
        with self._lock:
            chars = self._characters.get(world_id, [])
            return [copy.deepcopy(c) for c in sorted(chars, key=lambda c: (c.sort_order, c.id))]

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
    def add_pairing_code(self, code: PairingCode) -> None:
        with self._lock:
            existing_id = self._code_by_hash.get(code.code_hash)
            if existing_id is not None:
                existing = self._codes[existing_id]
                if not existing.is_expired(code.created_at) and not existing.is_exhausted():
                    raise ValueError("an active pairing code with this value already exists")
            self._codes[code.id] = copy.deepcopy(code)
            self._code_by_hash[code.code_hash] = code.id

    def get_pairing_code_by_hash(self, code_hash: str) -> PairingCode | None:
        with self._lock:
            code_id = self._code_by_hash.get(code_hash)
            return copy.deepcopy(self._codes[code_id]) if code_id else None

    def consume_pairing_code(self, code_id: str, now: datetime) -> PairingCode:
        with self._lock:
            code = self._codes[code_id]
            if code.is_expired(now):
                raise PairingCodeRejected("expired")
            if code.is_exhausted():
                raise PairingCodeRejected("exhausted")
            code.used_count += 1
            return copy.deepcopy(code)

    # device input
    def add_device_input(self, item: DeviceInput) -> None:
        with self._lock:
            self._inputs.append(copy.deepcopy(item))

    def list_device_inputs(self, world_id: str) -> list[DeviceInput]:
        """Not part of the Protocol; handy for tests/debugging."""
        with self._lock:
            return [copy.deepcopy(i) for i in self._inputs if i.world_id == world_id]
