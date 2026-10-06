"""Admin operations behind the dashboard: list / create / adjust Worlds and watch many at once.

Same rules as the device API: no simulation logic here, persisted daily plans are never
rewritten, and every change only affects what is generated (or displayed) from now on.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from zoneinfo import ZoneInfo

from worldpane_core.catalog import CONTEXTS, build_shared_event_config, materialize
from worldpane_core.profiles import OFFICIAL_PROFILES

from . import schemas
from .domain import RELATIONSHIP_TYPES, Character, World
from .security import new_id
from .seed import build_world_with_defaults, official_profile
from .services import ServiceError, WorldService

# Top-level keys of worlds.shared_event_config the generator reads (worldpane-core).
SHARED_CONFIG_KEYS = {"attempts", "trigger_probability", "slot_step_min", "max_slot_tries", "overrides"}
MONITOR_LIMIT = 48
RELATIONSHIP_REQUIREMENTS = {"any", *RELATIONSHIP_TYPES}


def _int_at_least(low: int) -> Callable[[object], bool]:
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= low


def _weight(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0


# Type and range of each shared-event field. Core coerces with int()/float() and checks little
# else, so "90", 1.7, true or -1 would be accepted and silently mean something else (a negative
# max_per_day makes the event never eligible); values must match these exactly.
FIELD_TYPES: dict[str, tuple[Callable[[object], bool], str]] = {
    "min_duration": (_int_at_least(1), "an integer >= 1"),
    "max_duration": (_int_at_least(1), "an integer >= 1"),
    "cooldown_min": (_int_at_least(0), "an integer >= 0"),
    "max_per_day": (_int_at_least(1), "an integer >= 1 (use enabled: false to turn the event off)"),
    "min_participants": (_int_at_least(2), "an integer >= 2"),
    "max_participants": (lambda v: v is None or _int_at_least(2)(v), "an integer >= 2 or null"),
    "weight": (_weight, "a finite number >= 0"),
    "label": (lambda v: isinstance(v, str) and 0 < len(v.strip()) <= 100, "a non-empty string"),
}


def _number(v: object) -> float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _override_problems(where: str, ov: object, fields: set[str], nested: bool = True) -> list[str]:
    """Checks core leaves to the generator: unknown fields (a typo such as "weigth" would be kept
    and silently do nothing), non-boolean ``enabled`` (core only tests truthiness, so "false"
    would enable) and ``context_overrides`` that are not ``{context: overrides}``."""
    if not isinstance(ov, dict):
        return []  # core reports non-object overrides itself
    allowed = fields | ({"context_overrides"} if nested else set())
    problems = [f"{where}.{k}: unknown field" for k in sorted(set(ov) - allowed)]
    if "enabled" in ov and not isinstance(ov["enabled"], bool):
        problems.append(f"{where}.enabled must be true or false")
    for name, (ok, expected) in FIELD_TYPES.items():
        if name in ov and not ok(ov[name]):
            problems.append(f"{where}.{name} must be {expected}")
    # Core only checks for a list of strings; an unknown context ("weekend") never matches, which
    # would silently switch the event off everywhere.
    allowed_context = ov.get("allowed_context")
    if isinstance(allowed_context, list):
        unknown = [c for c in allowed_context if isinstance(c, str) and c not in CONTEXTS]
        if unknown:
            problems.append(f"{where}.allowed_context: unknown context {', '.join(map(str, unknown))} "
                            f"(one of {', '.join(CONTEXTS)})")
    # Core matches it against a set of relationship types: anything unhashable would crash plans.
    required = ov.get("relationship_required")
    if required is not None and (not isinstance(required, str) or required not in RELATIONSHIP_REQUIREMENTS):
        problems.append(f"{where}.relationship_required must be null, \"any\" or one of "
                        f"{', '.join(RELATIONSHIP_TYPES)}")
    contexts = ov.get("context_overrides") if nested else None
    if isinstance(contexts, dict):
        for ctx, ctx_ov in contexts.items():
            if ctx not in CONTEXTS:
                problems.append(f"{where}.context_overrides.{ctx}: unknown context "
                                f"(one of {', '.join(CONTEXTS)})")
            elif not isinstance(ctx_ov, dict):
                problems.append(f"{where}.context_overrides.{ctx} must be an object")
            else:
                problems += _override_problems(f"{where}.context_overrides.{ctx}", ctx_ov, fields, nested=False)
    elif contexts is not None:
        problems.append(f"{where}.context_overrides must be an object of context -> overrides")
    return problems


class AdminService:
    def __init__(self, service: WorldService) -> None:
        self.service = service
        self.repo = service.repo

    # --- reads ------------------------------------------------------------------------------
    @staticmethod
    def profiles() -> list[schemas.AdminProfile]:
        return [schemas.AdminProfile(key=key, name=name) for key, (name, _) in OFFICIAL_PROFILES.items()]

    def list_worlds(self) -> list[schemas.AdminWorldSummary]:
        return [schemas.AdminWorldSummary(**vars(w)) for w in self.repo.list_world_summaries()]

    def world(self, world_id: str) -> schemas.AdminWorld:
        world = self.service._world(world_id)
        characters = self.repo.list_characters(world.id, include_archived=True)
        characters.sort(key=lambda c: c.archived_at is not None)  # stable: keeps display order
        return schemas.AdminWorld(
            id=world.id, name=world.name, timezone=world.timezone,
            simulation_start_date=world.simulation_start_date, created_at=world.created_at,
            revision=world.revision, shared_event_config=world.shared_event_config,
            shared_events=[
                schemas.AdminSharedEvent(key=ev["type"], label=ev.get("label", ev["type"]),
                                         enabled=bool(ev.get("enabled", True)), weight=_number(ev.get("weight")))
                for ev in (materialize(d) for d in sorted(world.shared_event_definitions,
                                                          key=lambda d: (d.sort_order, d.key)))
            ],
            characters=[
                schemas.AdminCharacter(
                    id=c.id, display_name=c.display_name, appearance=c.appearance_key,
                    profile_key=c.profile.key, profile_name=c.profile.name or c.profile.key or "",
                    sort_order=c.sort_order, archived_at=c.archived_at,
                )
                for c in characters
            ],
            devices=[
                schemas.AdminDevice(id=d.id, firmware_version=d.firmware_version,
                                    created_at=d.created_at, last_seen_at=d.last_seen_at)
                for d in self.repo.list_devices(world.id)
            ],
        )

    def monitor(self, world_ids: list[str]) -> schemas.Monitor:
        """Current state of several Worlds in one call (the dashboard's monitor wall)."""
        if not world_ids:
            world_ids = [w.id for w in self.repo.list_world_summaries()]
        out: list[schemas.MonitorWorld] = []
        for world_id in list(dict.fromkeys(world_ids))[:MONITOR_LIMIT]:
            world = self.repo.get_world(world_id)
            if world is None:
                continue  # deleted meanwhile; the dashboard drops the tile
            state = self.service.device_state(world.id).state
            names = {c.id: c.display_name for c in self.repo.list_characters(world.id)}
            out.append(schemas.MonitorWorld(
                world_id=world.id, name=world.name, timezone=world.timezone,
                server_time=state.server_time, revision=state.revision,
                characters=[
                    schemas.MonitorCharacter(**c.model_dump(), display_name=names.get(c.id, ""))
                    for c in state.characters
                ],
            ))
        return schemas.Monitor(worlds=out)

    # --- writes -----------------------------------------------------------------------------
    @staticmethod
    def _profile(key: str):
        if key not in OFFICIAL_PROFILES:
            raise ServiceError(422, "unknown_profile", f"Unknown profile: {key}")
        return official_profile(key)

    def create_world(self, body: schemas.AdminCreateWorldIn) -> schemas.AdminCreateWorldOut:
        now = self.service.clock.now()
        tz_name = body.timezone or self.service.settings.default_timezone
        world_id = new_id()
        characters = None
        if body.characters is not None:
            characters = [
                Character(id=new_id(), world_id=world_id, appearance_key=c.appearance,
                          display_name=c.display_name, profile=self._profile(c.profile_key), sort_order=i)
                for i, c in enumerate(body.characters)
            ]
        world, chars, rels = build_world_with_defaults(
            world_id=world_id, name=body.name, timezone=tz_name, created_at=now,
            start_date=now.astimezone(ZoneInfo(tz_name)).date(),
            characters=characters,
        )
        for _ in range(20):
            pc, pairing = self.service._new_pairing_code(world, body.pairing_max_uses, None)
            try:
                self.repo.create_world(world, chars, rels, [], [pc])
            except ValueError:
                continue  # the pairing code collided with an active one; draw again
            return schemas.AdminCreateWorldOut(world=self.world(world.id), pairing=pairing)
        raise ServiceError(503, "pairing_code_unavailable", "Could not allocate a pairing code, retry")

    def update_world(self, world_id: str, body: schemas.AdminWorldPatch) -> schemas.AdminWorld:
        world = self.service._world(world_id)
        cfg = body.shared_event_config
        if cfg is not None:
            self._check_shared_config(world, cfg)
        self.repo.update_world(world.id, name=body.name, shared_event_config=cfg)
        return self.world(world.id)

    @staticmethod
    def _check_shared_config(world: World, cfg: dict) -> None:
        problems = [f"unknown key: {k}" for k in sorted(set(cfg) - SHARED_CONFIG_KEYS)]
        overrides = cfg.get("overrides")
        if overrides is not None and not isinstance(overrides, dict):
            problems.append("overrides must be an object of event key -> overrides")
        elif isinstance(overrides, dict):
            known = {d.key for d in world.shared_event_definitions}
            problems += [f"overrides.{k}: unknown shared event" for k in sorted(set(overrides) - known)]
            # Fields a shared event has once materialised; "type" is its identity, not a setting.
            fields = {f for d in world.shared_event_definitions for f in materialize(d)} - {"type"}
            for key, ov in overrides.items():
                problems += _override_problems(f"overrides.{key}", ov, fields)
        # worldpane-core skips bad values at generation time; here they are a 422 instead.
        build_shared_event_config(cfg, world.shared_event_definitions, on_invalid=problems.append)
        if problems:
            # Core phrases them for its skip-and-continue mode ("...; using the default").
            reasons = [p.split("; using")[0].split("; ignoring")[0] for p in problems]
            raise ServiceError(422, "invalid_shared_event_config", "; ".join(reasons))

    def _character(self, world_id: str, character_id: str) -> Character:
        self.service._world(world_id)
        for c in self.repo.list_characters(world_id, include_archived=True):
            if c.id == character_id:
                return c
        raise ServiceError(404, "character_not_found", "Character not found in this World")

    def add_character(self, world_id: str, body: schemas.AdminCharacterIn) -> schemas.AdminWorld:
        """New characters join plans generated from now on; a day already planned stays as is.
        The repository places it last and relates it ("friend") to every active character."""
        world = self.service._world(world_id)
        character = Character(
            id=new_id(), world_id=world.id, appearance_key=body.appearance,
            display_name=body.display_name, profile=self._profile(body.profile_key),
        )
        self.repo.add_character(character, relationship_type="friend")
        return self.world(world.id)

    def update_character(self, world_id: str, character_id: str,
                         body: schemas.AdminCharacterPatch) -> schemas.AdminWorld:
        c = self._character(world_id, character_id)
        self.repo.update_character(c.id, display_name=body.display_name,
                                   appearance_key=body.appearance, sort_order=body.sort_order)
        return self.world(world_id)

    def archive_character(self, world_id: str, character_id: str) -> schemas.AdminWorld:
        c = self._character(world_id, character_id)
        if not self.repo.archive_character(c.id, self.service.clock.now(), keep_one_active=True):
            raise ServiceError(409, "last_character", "A World needs at least one active character")
        return self.world(world_id)
