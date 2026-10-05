-- =============================================================================
-- Worldpane — event catalog (data-driven, extensible events) + device inputs
--
-- Goal: adding a new life event = INSERT a row, never a code change or
-- firmware re-flash (spec §30). Every tunable value spec §34 leaves TBD
-- (weights, durations, cooldowns, probabilities) lives in the database:
--
--   * event_definitions.params        — per-event knobs (+ context_overrides)
--   * profile_event_pools.overrides   — per-profile tweaks of one event
--   * character_profiles.*_config     — schedule / meal / leave / attempt knobs
--   * worlds.shared_event_config      — world shared-event knobs (+ overrides)
--
-- worldpane-core assembles these into its generator config
-- (worldpane_core.catalog.build_event_config / build_shared_event_config).
-- Edits only affect daily plans generated afterwards; persisted plans are
-- immutable history (spec §15, §17).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- event_definitions — one row per event type.
-- -----------------------------------------------------------------------------

create table worldpane.event_definitions (
  id          uuid primary key default gen_random_uuid(),
  -- NULL = official definition visible to every world. Non-NULL = owned by
  -- one world; a world definition with the same (category, key) as an
  -- official one shadows it for that world.
  world_id    uuid references worldpane.worlds (id) on delete cascade,
  key         text not null check (key ~ '^[a-z0-9_]{1,64}$'),
  -- temporary = interruption inside a work/school block (spec §7, §9)
  -- leisure   = individual life event (spec §10, §13)
  -- shared    = one event with 2..N participants (spec §11)
  -- Base schedule and meals are profile structure, not catalog entries.
  category    text not null check (category in ('temporary', 'leisure', 'shared')),
  label       text not null check (char_length(btrim(label)) between 1 and 50),
  -- Display semantics. temporary events inherit scene/location from the
  -- work/school block, so these may be NULL there.
  scene       text check (scene is null or scene ~ '^[a-z0-9_]{1,64}$'),
  location    text check (location is null or location ~ '^[A-Za-z0-9_]{1,64}$'),
  activity    text check (activity is null or activity ~ '^[a-z0-9_]{1,64}$'),
  -- All tunables. Recognised keys (unknown keys are ignored by the core):
  --   weight, min_duration, max_duration, cooldown_min,
  --   allowed_time [["HH:MM","HH:MM"], ...], allowed_context ["weekday","holiday","leave"],
  --   context_overrides {"holiday": {"weight": 40, "enabled": false, ...}},
  --   shared only: min_participants, max_participants (null = N),
  --                relationship_required (null | "any" | relationship_type), max_per_day
  params      jsonb not null default '{}'::jsonb check (jsonb_typeof(params) = 'object'),
  enabled     boolean not null default true,
  -- Draw order feeds the deterministic RNG, so it must be stable:
  -- the core always sorts by (sort_order, key).
  sort_order  integer not null default 100,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

comment on table worldpane.event_definitions is
  'Data-driven event catalog. New events are new rows; the Simulation Core has no per-event code. '
  'params carries every spec §34 TBD value for the event. Validated by worldpane_core.catalog.validate_definition when loaded.';

create unique index event_definitions_official_uq
  on worldpane.event_definitions (category, key) where world_id is null;
create unique index event_definitions_world_uq
  on worldpane.event_definitions (world_id, category, key) where world_id is not null;

create trigger event_definitions_set_updated_at
  before update on worldpane.event_definitions
  for each row execute function worldpane.tg_set_updated_at();

-- -----------------------------------------------------------------------------
-- profile_event_pools — which temporary / leisure events a profile can draw,
-- with optional per-profile overrides (merged over params).
-- Shared events are world-level: every enabled shared definition visible to
-- the world applies, tuned via worlds.shared_event_config.overrides.
-- -----------------------------------------------------------------------------

create table worldpane.profile_event_pools (
  profile_id          uuid not null references worldpane.character_profiles (id) on delete cascade,
  event_definition_id uuid not null references worldpane.event_definitions (id) on delete cascade,
  overrides           jsonb not null default '{}'::jsonb check (jsonb_typeof(overrides) = 'object'),
  enabled             boolean not null default true,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  primary key (profile_id, event_definition_id)
);

comment on table worldpane.profile_event_pools is
  'Profile -> event definitions (temporary / leisure only). overrides are deep-merged over the definition (e.g. {"weight": 5}).';

create index profile_event_pools_definition_idx
  on worldpane.profile_event_pools (event_definition_id);

create trigger profile_event_pools_set_updated_at
  before update on worldpane.profile_event_pools
  for each row execute function worldpane.tg_set_updated_at();

-- Pool entries must be temporary/leisure, and a profile may only use official
-- definitions or definitions of its own world.
create or replace function worldpane.tg_check_profile_event_pool()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  v_profile_world uuid;
  v_def_world     uuid;
  v_category      text;
begin
  select p.world_id into v_profile_world
    from worldpane.character_profiles p where p.id = new.profile_id;
  select d.world_id, d.category into v_def_world, v_category
    from worldpane.event_definitions d where d.id = new.event_definition_id;
  if v_category not in ('temporary', 'leisure') then
    raise exception 'event definition % is %, only temporary/leisure belong in a profile pool',
      new.event_definition_id, v_category using errcode = '23514';
  end if;
  if v_def_world is not null and v_def_world is distinct from v_profile_world then
    raise exception 'event definition % belongs to another world', new.event_definition_id
      using errcode = '23514';
  end if;
  return new;
end;
$$;

create trigger profile_event_pools_check
  before insert or update on worldpane.profile_event_pools
  for each row execute function worldpane.tg_check_profile_event_pool();

-- -----------------------------------------------------------------------------
-- device_inputs — button presses etc. (spec §21 POST /device/input). Logged
-- only in V1; the simulation does not consume them yet.
-- -----------------------------------------------------------------------------

create table worldpane.device_inputs (
  id          uuid primary key default gen_random_uuid(),
  device_id   uuid not null references worldpane.devices (id) on delete cascade,
  world_id    uuid references worldpane.worlds (id) on delete set null,
  type        text not null check (type ~ '^[a-z0-9_]{1,32}$'),
  button      text check (button is null or char_length(button) <= 16),
  payload     jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  received_at timestamptz not null default now()
);

create index device_inputs_device_idx on worldpane.device_inputs (device_id, received_at desc);

-- -----------------------------------------------------------------------------
-- RLS + privileges (same model as the init migration: service_role only).
-- -----------------------------------------------------------------------------

alter table worldpane.event_definitions   enable row level security;
alter table worldpane.profile_event_pools enable row level security;
alter table worldpane.device_inputs       enable row level security;

revoke all on worldpane.event_definitions, worldpane.profile_event_pools, worldpane.device_inputs from public;
revoke all on function worldpane.tg_check_profile_event_pool() from public;

grant select, insert, update, delete
  on worldpane.event_definitions, worldpane.profile_event_pools, worldpane.device_inputs
  to service_role;
grant execute on function worldpane.tg_check_profile_event_pool() to service_role;
