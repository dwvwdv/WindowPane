-- =============================================================================
-- Worldpane / 窗間 — initial schema
--
-- Everything lives in the dedicated `worldpane` schema (NOT `public`): the
-- Supabase project hosts several apps, each isolated in its own schema.
--
-- Access model (spec §3): V1 has NO user accounts. Devices authenticate to the
-- FastAPI backend (worldpane-server) with a device token; the backend talks to
-- Postgres with the Supabase `service_role` (BYPASSRLS). Therefore:
--   * RLS is ENABLED on every table and NO policies exist  -> deny-by-default
--     for `anon` / `authenticated` even if the schema were ever exposed.
--   * Only `service_role` gets USAGE on the schema and privileges on objects.
-- When user accounts arrive (User -> World -> Device), add policies then.
--
-- Spec references: §2–4 (World aggregate), §11 (shared events 2..N),
-- §12 (relationships, no partner_id), §15 (deterministic daily plan),
-- §17 (event log history), §19–21 (Display API revision / ETag),
-- §22 (pairing), §23 (device preference), §28 (conceptual model),
-- §29 (what not to store), §31 (invariants).
--
-- gen_random_uuid() is built into PostgreSQL >= 13, so pgcrypto is not needed.
-- Token / pairing-code hashing happens in the backend (HMAC with a server-side
-- secret — a 6-digit code hashed with plain sha256 is trivially reversible).
-- =============================================================================

create schema if not exists worldpane;

comment on schema worldpane is
  'Worldpane (窗間) app schema. V1: no user accounts; all access via the FastAPI backend using service_role. RLS on, no policies (deny-by-default).';

-- -----------------------------------------------------------------------------
-- Enums
-- -----------------------------------------------------------------------------

-- Spec §14 priority ladder. Enum order == priority order (fixed is highest),
-- so `ORDER BY priority` sorts highest-priority first.
create type worldpane.event_priority as enum (
  'fixed',              -- 1. Fixed / mandatory event (work / school base schedule, leave)
  'meal',               -- 2. Meal
  'shared',             -- 3. Shared / group event
  'temporary',          -- 4. Work / School temporary event (slacking, sleeping in class)
  'individual_leisure', -- 5. Individual leisure event
  'idle'                -- 6. Idle
);

-- Persisted lifecycle only. "active" / "completed" are NOT stored: they are
-- derived from start_at/end_at vs. now() (no cron jobs, spec §15).
create type worldpane.event_status as enum (
  'scheduled',
  'cancelled'           -- e.g. displaced by a higher-priority event (spec §14)
);

create type worldpane.pairing_consumed_reason as enum (
  'exhausted',          -- used_count reached max_uses
  'expired',            -- found past expires_at (marked lazily)
  'revoked'             -- revoked by the backend / world owner
);

-- Result of worldpane.redeem_pairing_code().
create type worldpane.pairing_result as (
  status   text,        -- ok | already_paired | invalid | expired | exhausted | device_not_found | device_revoked
  world_id uuid         -- set for ok / already_paired; NULL otherwise
);

-- -----------------------------------------------------------------------------
-- Helper trigger functions
-- -----------------------------------------------------------------------------

create or replace function worldpane.tg_set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- Validate IANA timezone names (spec §4: every World has its own timezone).
-- A CHECK constraint cannot query pg_timezone_names, so a trigger is used.
create or replace function worldpane.tg_validate_world_timezone()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if not exists (select 1 from pg_catalog.pg_timezone_names where name = new.timezone) then
    raise exception 'invalid timezone: %', new.timezone
      using errcode = '22023';
  end if;
  return new;
end;
$$;

-- -----------------------------------------------------------------------------
-- worlds — aggregate root (spec §4)
-- -----------------------------------------------------------------------------

create table worldpane.worlds (
  id                    uuid primary key default gen_random_uuid(),
  name                  text not null check (char_length(btrim(name)) between 1 and 100),
  timezone              text not null default 'Asia/Taipei',
  -- Current simulation algorithm version. Bumping it makes new daily plans
  -- be generated under the new version (spec §15). Old plans stay as history.
  simulation_version    integer not null default 1 check (simulation_version >= 1),
  -- First local date the world simulates; no plans before this date.
  simulation_start_date date not null,
  -- World-level Shared / Group Event Rules (spec §4, §11–13): min/max
  -- participants, relationship_required, weight, duration, allowed time /
  -- context, cooldown. Per-character rules live in character_profiles.
  shared_event_config   jsonb not null default '{}'::jsonb check (jsonb_typeof(shared_event_config) = 'object'),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

comment on table worldpane.worlds is
  'Aggregate root (spec §4). 1 World : N Characters, N Devices, N Events. Character count is never hard-coded (invariant 7).';

create trigger worlds_validate_timezone
  before insert or update of timezone on worldpane.worlds
  for each row execute function worldpane.tg_validate_world_timezone();

create trigger worlds_set_updated_at
  before update on worldpane.worlds
  for each row execute function worldpane.tg_set_updated_at();

-- -----------------------------------------------------------------------------
-- world_revisions — monotonically increasing counter per world for the
-- Display API `revision` field and ETag (spec §19–20).
-- -----------------------------------------------------------------------------

create table worldpane.world_revisions (
  world_id   uuid primary key references worldpane.worlds (id) on delete cascade,
  revision   bigint not null default 1 check (revision >= 1),
  -- Fingerprint of the last Display State served. The display state changes
  -- with time even without writes (an event ends), so the backend bumps the
  -- revision when the fingerprint changes (see worldpane-server).
  state_fingerprint text,
  updated_at timestamptz not null default now()
);

comment on table worldpane.world_revisions is
  'One row per world. revision is bumped (by triggers) whenever world-visible data changes: world name/timezone/version, characters, events, event participants, relationships. '
  'NOTE: the current display state also changes as time passes with no DB write (an event starts/ends), so the backend ETag must combine '
  'this revision with the ids of the currently active events (and the device preference revision for per-device state).';

-- Bump the revision of one world. UPDATE-only on purpose: during a cascading
-- world delete the row may already be gone, and we must not re-insert it.
create or replace function worldpane.bump_world_revision(p_world_id uuid)
returns void
language sql
set search_path = ''
as $$
  update worldpane.world_revisions
     set revision = revision + 1,
         updated_at = now()
   where world_id = p_world_id;
$$;

create or replace function worldpane.tg_world_created()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  insert into worldpane.world_revisions (world_id) values (new.id);
  return new;
end;
$$;

create trigger worlds_create_revision
  after insert on worldpane.worlds
  for each row execute function worldpane.tg_world_created();

-- Generic row trigger for tables that carry a world_id column.
create or replace function worldpane.tg_bump_world_revision()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op in ('UPDATE', 'DELETE') then
    perform worldpane.bump_world_revision(old.world_id);
  end if;
  if tg_op in ('INSERT', 'UPDATE')
     and (tg_op = 'INSERT' or new.world_id is distinct from old.world_id) then
    perform worldpane.bump_world_revision(new.world_id);
  end if;
  return null; -- AFTER trigger
end;
$$;

create or replace function worldpane.tg_world_changed()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  perform worldpane.bump_world_revision(new.id);
  return null;
end;
$$;

create trigger worlds_bump_revision
  after update of name, timezone, simulation_version, shared_event_config on worldpane.worlds
  for each row execute function worldpane.tg_world_changed();

-- -----------------------------------------------------------------------------
-- character_profiles — behaviour rules (spec §6–10). Appearance is NOT here.
-- -----------------------------------------------------------------------------

create table worldpane.character_profiles (
  id              uuid primary key default gen_random_uuid(),
  -- NULL world_id = official / shared template profile (e.g. official student
  -- profile) that many worlds' characters may reference. Non-NULL = a profile
  -- owned by (customised for) one world.
  world_id        uuid references worldpane.worlds (id) on delete cascade,
  -- Stable key for templates, e.g. 'official.student.v1'.
  key             text check (key is null or key ~ '^[a-z0-9_.-]{1,100}$'),
  name            text not null check (char_length(btrim(name)) between 1 and 100),
  -- Weekly base schedule, location/activity per block (spec §7, §9).
  schedule_config jsonb not null default '{}'::jsonb check (jsonb_typeof(schedule_config) = 'object'),
  -- Meals: windows, durations, skip probabilities, min interval (spec §8).
  meal_config     jsonb not null default '{}'::jsonb check (jsonb_typeof(meal_config) = 'object'),
  -- Leave rules: monthly or fixed-anchor N-day cycle (spec §7).
  leave_config    jsonb not null default '{}'::jsonb check (jsonb_typeof(leave_config) = 'object'),
  -- Temporary (work/school) + leisure event definitions, weights, context overrides (spec §7, §10, §13).
  event_config    jsonb not null default '{}'::jsonb check (jsonb_typeof(event_config) = 'object'),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

comment on table worldpane.character_profiles is
  'CharacterProfile (spec §6): schedule / meal / leave / event rules as jsonb. Values marked TBD in spec §34 must live here, never in the Simulation Core. '
  'Editing a profile only affects plans generated afterwards; persisted daily plans are immutable history.';

create unique index character_profiles_template_key_uq
  on worldpane.character_profiles (key) where world_id is null and key is not null;
create unique index character_profiles_world_key_uq
  on worldpane.character_profiles (world_id, key) where world_id is not null and key is not null;
create index character_profiles_world_idx
  on worldpane.character_profiles (world_id) where world_id is not null;

create trigger character_profiles_set_updated_at
  before update on worldpane.character_profiles
  for each row execute function worldpane.tg_set_updated_at();

-- -----------------------------------------------------------------------------
-- characters — character instances (spec §5). Same appearance in two worlds
-- = two different rows (invariant 6).
-- -----------------------------------------------------------------------------

create table worldpane.characters (
  id             uuid primary key default gen_random_uuid(),
  world_id       uuid not null references worldpane.worlds (id) on delete cascade,
  -- Appearance key the device maps to local assets (spec §6, §24). e.g. 'xiaobai'.
  appearance_key text not null check (appearance_key ~ '^[a-z0-9_-]{1,64}$'),
  display_name   text not null check (char_length(btrim(display_name)) between 1 and 50),
  -- Behaviour. RESTRICT: a profile in use cannot be deleted.
  profile_id     uuid not null references worldpane.character_profiles (id) on delete restrict,
  sort_order     integer not null default 0,
  -- Soft delete: history (events) must survive (spec §17), so characters that
  -- ever participated in an event are archived instead of deleted.
  archived_at    timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  -- Target for composite FKs that guarantee "same world" integrity.
  unique (id, world_id)
);

comment on table worldpane.characters is
  'Character instance = appearance + profile (spec §5–6). 1..N per world; no fixed count, no partner_id (invariants 7, 12).';

create index characters_world_idx on worldpane.characters (world_id, sort_order);
create index characters_profile_idx on worldpane.characters (profile_id);

create trigger characters_set_updated_at
  before update on worldpane.characters
  for each row execute function worldpane.tg_set_updated_at();

create trigger characters_bump_revision
  after insert or update or delete on worldpane.characters
  for each row execute function worldpane.tg_bump_world_revision();

-- A world-owned profile may only be used by characters of that same world.
create or replace function worldpane.tg_check_character_profile_world()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  v_profile_world uuid;
begin
  select p.world_id into v_profile_world
    from worldpane.character_profiles p
   where p.id = new.profile_id;
  if v_profile_world is not null and v_profile_world <> new.world_id then
    raise exception 'profile % belongs to another world', new.profile_id
      using errcode = '23514';
  end if;
  return new;
end;
$$;

create trigger characters_check_profile_world
  before insert or update of profile_id, world_id on worldpane.characters
  for each row execute function worldpane.tg_check_character_profile_world();

-- -----------------------------------------------------------------------------
-- character_relationships (spec §12) — undirected, one row per unordered pair.
-- -----------------------------------------------------------------------------

create table worldpane.character_relationships (
  id                uuid primary key default gen_random_uuid(),
  world_id          uuid not null references worldpane.worlds (id) on delete cascade,
  character_a_id    uuid not null,
  character_b_id    uuid not null,
  relationship_type text not null,
  -- V1 does not implement an affinity system (spec §12, §33); kept nullable.
  affinity          numeric(6, 2),
  metadata          jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  constraint character_relationships_distinct_chk check (character_a_id <> character_b_id),
  -- Extend this list with a new migration when new relationship kinds appear.
  constraint character_relationships_type_chk check (relationship_type in (
    'couple', 'friend', 'roommate', 'family', 'sibling', 'classmate', 'colleague', 'other'
  )),
  -- Both characters must belong to the relationship's world.
  constraint character_relationships_a_fk foreign key (character_a_id, world_id)
    references worldpane.characters (id, world_id) on delete cascade,
  constraint character_relationships_b_fk foreign key (character_b_id, world_id)
    references worldpane.characters (id, world_id) on delete cascade
);

comment on table worldpane.character_relationships is
  'Undirected relationship between two characters of the same world (spec §12). Replaces any partner_id. (A,B) and (B,A) are the same pair: enforced by a unique index on (least, greatest).';

create unique index character_relationships_pair_uq
  on worldpane.character_relationships (
    world_id,
    least(character_a_id, character_b_id),
    greatest(character_a_id, character_b_id)
  );
create index character_relationships_a_idx on worldpane.character_relationships (character_a_id);
create index character_relationships_b_idx on worldpane.character_relationships (character_b_id);

create trigger character_relationships_set_updated_at
  before update on worldpane.character_relationships
  for each row execute function worldpane.tg_set_updated_at();

create trigger character_relationships_bump_revision
  after insert or update or delete on worldpane.character_relationships
  for each row execute function worldpane.tg_bump_world_revision();

-- -----------------------------------------------------------------------------
-- daily_plans — one deterministic plan per (world, local_date, simulation_version)
-- (spec §15). Guarantees a day is never persisted twice for the same version.
-- -----------------------------------------------------------------------------

create table worldpane.daily_plans (
  id                 uuid primary key default gen_random_uuid(),
  world_id           uuid not null references worldpane.worlds (id) on delete cascade,
  -- Calendar date in the WORLD's timezone (spec §4).
  local_date         date not null,
  simulation_version integer not null check (simulation_version >= 1),
  -- Resolved calendar context, seeds used (character-local + world 'shared'),
  -- leave decisions, generator diagnostics... Informational / for bug repro.
  metadata           jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  generated_at       timestamptz not null default now(),
  -- When a newer simulation_version replaces this plan for the same date, set
  -- superseded_at; at most one non-superseded plan per (world, date).
  superseded_at      timestamptz,
  constraint daily_plans_world_date_version_uq unique (world_id, local_date, simulation_version),
  unique (id, world_id)
);

comment on table worldpane.daily_plans is
  'Deterministic daily plan header (spec §15). UNIQUE (world_id, local_date, simulation_version) makes persisting idempotent: '
  'INSERT ... ON CONFLICT DO NOTHING, then insert events only if the plan row was created. The plan covers all characters of the world '
  '(shared events are world-level). The "current" plan of a date is the one with superseded_at IS NULL.';

create unique index daily_plans_current_uq
  on worldpane.daily_plans (world_id, local_date) where superseded_at is null;

-- -----------------------------------------------------------------------------
-- events — event log / history (spec §17). Times are absolute timestamptz;
-- world-local rendering uses worlds.timezone.
-- -----------------------------------------------------------------------------

create table worldpane.events (
  id            uuid primary key default gen_random_uuid(),
  world_id      uuid not null references worldpane.worlds (id) on delete cascade,
  daily_plan_id uuid not null,
  -- Activity key, e.g. 'school', 'sleeping_in_class', 'breakfast', 'reading', 'movie'.
  type          text not null check (type ~ '^[a-z0-9_]{1,64}$'),
  -- Scene the device renders, e.g. 'school_classroom', 'home_living_room' (spec §19).
  scene         text not null check (scene ~ '^[a-z0-9_]{1,64}$'),
  -- Semantic state (spec §9: state = location + activity), e.g. OFFICE / slacking.
  location      text check (location is null or location ~ '^[A-Za-z0-9_]{1,64}$'),
  activity      text not null check (activity ~ '^[a-z0-9_]{1,64}$'),
  -- 'base' = background schedule block (SCHOOL 08:30–17:30) that foreground
  -- events (meal, slacking, ...) overlay; 'foreground' = everything else.
  layer         text not null default 'foreground' check (layer in ('base', 'foreground')),
  priority      worldpane.event_priority not null,
  status        worldpane.event_status not null default 'scheduled',
  start_at      timestamptz not null,
  end_at        timestamptz not null,
  metadata      jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint events_time_order_chk check (end_at > start_at),
  constraint events_daily_plan_fk foreign key (daily_plan_id, world_id)
    references worldpane.daily_plans (id, world_id) on delete cascade,
  unique (id, world_id)
);

comment on table worldpane.events is
  'Event log (spec §17). A shared/group event is ONE row with 2..N participants (invariant 8). simulation_version is taken from the daily plan. '
  'Per-character NO-OVERLAP is enforced by the Simulation Core conflict resolver (spec §14), NOT by the database: whether base schedule '
  'blocks (WORK/SCHOOL) are stored as split segments or as a layer under temporary events is a Core decision, and a DB exclusion '
  'constraint would forbid the layered representation. If the Core settles on strictly non-overlapping segments, add: '
  'btree_gist + a denormalized tstzrange on event_participants + EXCLUDE USING gist (character_id WITH =, during WITH &&) WHERE (status = ''scheduled'').';

-- Range lookups: "events of world W overlapping [from, to)" =>
--   where world_id = $1 and start_at < $to and end_at > $from
-- Events are bounded (< 1 day), so callers may also add start_at > $from - interval '1 day'
-- to keep the btree range scan tight.
create index events_world_time_idx on worldpane.events (world_id, start_at, end_at);
create index events_daily_plan_idx on worldpane.events (daily_plan_id);

create trigger events_set_updated_at
  before update on worldpane.events
  for each row execute function worldpane.tg_set_updated_at();

create trigger events_bump_revision
  after insert or update or delete on worldpane.events
  for each row execute function worldpane.tg_bump_world_revision();

-- -----------------------------------------------------------------------------
-- event_participants (spec §11, §17). world_id is denormalized so composite
-- FKs guarantee event and character are in the same world.
-- -----------------------------------------------------------------------------

create table worldpane.event_participants (
  event_id     uuid not null,
  character_id uuid not null,
  world_id     uuid not null,
  -- Optional role inside a group event (e.g. 'host'); NULL for individual events.
  role         text check (role is null or role ~ '^[a-z0-9_]{1,32}$'),
  created_at   timestamptz not null default now(),
  primary key (event_id, character_id),
  constraint event_participants_event_fk foreign key (event_id, world_id)
    references worldpane.events (id, world_id) on delete cascade,
  -- NO ACTION: a character that appears in history cannot be hard-deleted
  -- (archive it instead, spec §17). Whole-world deletes still work because
  -- worlds_delete_events_first removes events (-> participants) beforehand.
  constraint event_participants_character_fk foreign key (character_id, world_id)
    references worldpane.characters (id, world_id) on delete no action
);

comment on table worldpane.event_participants is
  'N:N Event <-> Character (spec §17). Participant-count rules (min/max participants, relationship_required) are Event Rule config validated by the Shared Event Scheduler.';

-- "Timeline of character C": join events on event_id, filter by time.
create index event_participants_character_idx on worldpane.event_participants (character_id, event_id);

create trigger event_participants_bump_revision
  after insert or update or delete on worldpane.event_participants
  for each row execute function worldpane.tg_bump_world_revision();

-- Deleting a world: remove its events (and, by cascade, participants) BEFORE
-- the FK cascades run, otherwise worlds -> characters would trip the NO ACTION
-- check on event_participants_character_fk (cascade order is not guaranteed).
create or replace function worldpane.tg_world_delete_events_first()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  delete from worldpane.events where world_id = old.id;
  return old;
end;
$$;

create trigger worlds_delete_events_first
  before delete on worldpane.worlds
  for each row execute function worldpane.tg_world_delete_events_first();

-- -----------------------------------------------------------------------------
-- devices (spec §18, §22). Device -> World is N:1; world_id NULL = registered
-- but not yet paired. Only a HASH of the device token is stored.
-- -----------------------------------------------------------------------------

create table worldpane.devices (
  id                uuid primary key default gen_random_uuid(),
  world_id          uuid references worldpane.worlds (id) on delete set null,
  -- HMAC/sha256 hex (or similar) of the device bearer token. Never plaintext.
  device_token_hash text not null check (char_length(device_token_hash) between 32 and 256),
  firmware_version  text check (firmware_version is null or char_length(firmware_version) <= 64),
  paired_at         timestamptz,
  last_seen_at      timestamptz,
  revoked_at        timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  constraint devices_token_hash_uq unique (device_token_hash)
);

comment on table worldpane.devices is
  'Physical window onto a world (spec §18, §22). One device shows one world at a time (invariant 4); one world has many devices (invariant 3).';

create index devices_world_idx on worldpane.devices (world_id) where world_id is not null;

create trigger devices_set_updated_at
  before update on worldpane.devices
  for each row execute function worldpane.tg_set_updated_at();

-- -----------------------------------------------------------------------------
-- device_preferences (spec §23, §29) — per-device display settings.
-- -----------------------------------------------------------------------------

create table worldpane.device_preferences (
  device_id            uuid primary key references worldpane.devices (id) on delete cascade,
  primary_character_id uuid references worldpane.characters (id) on delete set null,
  -- e.g. 'primary_character', 'group_overview' (spec §23). Free-form key so
  -- firmware can add layouts without a migration.
  layout               text not null default 'primary_character' check (layout ~ '^[a-z0-9_]{1,32}$'),
  brightness           smallint check (brightness between 0 and 100),
  history_display_mode text check (history_display_mode is null or history_display_mode ~ '^[a-z0-9_]{1,32}$'),
  config               jsonb not null default '{}'::jsonb check (jsonb_typeof(config) = 'object'),
  -- Per-device revision, to combine with world_revisions.revision in the ETag.
  revision             bigint not null default 1,
  updated_at           timestamptz not null default now()
);

comment on table worldpane.device_preferences is
  'Display preference per device (spec §23). World state is shared; preferences are per device. Assets/sprites/Wi-Fi are NOT stored here (spec §29).';

create index device_preferences_character_idx
  on worldpane.device_preferences (primary_character_id) where primary_character_id is not null;

create or replace function worldpane.tg_device_preferences_before_write()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  -- primary character must belong to the device's current world.
  if new.primary_character_id is not null and not exists (
    select 1
      from worldpane.devices d
      join worldpane.characters c on c.world_id = d.world_id
     where d.id = new.device_id
       and c.id = new.primary_character_id
  ) then
    raise exception 'primary_character % is not in the world of device %',
      new.primary_character_id, new.device_id
      using errcode = '23514';
  end if;
  if tg_op = 'UPDATE' then
    new.revision := old.revision + 1;
  end if;
  new.updated_at := now();
  return new;
end;
$$;

create trigger device_preferences_before_write
  before insert or update on worldpane.device_preferences
  for each row execute function worldpane.tg_device_preferences_before_write();

-- -----------------------------------------------------------------------------
-- pairing_codes (spec §22) — short-lived, hashed, limited-use.
-- -----------------------------------------------------------------------------

create table worldpane.pairing_codes (
  id              uuid primary key default gen_random_uuid(),
  world_id        uuid not null references worldpane.worlds (id) on delete cascade,
  -- HMAC(server_secret, code). The plaintext code and the world id are never
  -- exposed through the code itself.
  code_hash       text not null check (char_length(code_hash) between 32 and 256),
  expires_at      timestamptz not null,
  max_uses        integer not null default 1 check (max_uses between 1 and 100),
  used_count      integer not null default 0,
  -- A code is live while consumed_at IS NULL and now() < expires_at.
  -- consumed_at is set when: used_count reaches max_uses ('exhausted'),
  -- a lookup finds it expired ('expired', lazily), or it is revoked.
  consumed_at     timestamptz,
  consumed_reason worldpane.pairing_consumed_reason,
  created_by_device_id uuid references worldpane.devices (id) on delete set null,
  created_at      timestamptz not null default now(),
  constraint pairing_codes_used_count_chk check (used_count between 0 and max_uses),
  constraint pairing_codes_consumed_chk check ((consumed_at is null) = (consumed_reason is null)),
  constraint pairing_codes_exhausted_chk check (used_count < max_uses or consumed_at is not null),
  constraint pairing_codes_expiry_chk check (expires_at > created_at)
);

comment on table worldpane.pairing_codes is
  'Pairing codes (spec §22). Only the HMAC of the code is stored. At most one unconsumed row per code_hash (partial unique index), '
  'so a 6-digit code space can be reused once old codes are consumed. Create via worldpane.create_pairing_code(), redeem via worldpane.redeem_pairing_code().';

-- Lookup + uniqueness among live codes.
create unique index pairing_codes_live_hash_uq
  on worldpane.pairing_codes (code_hash) where consumed_at is null;
create index pairing_codes_world_idx on worldpane.pairing_codes (world_id);
-- For periodic cleanup of old rows.
create index pairing_codes_expires_idx on worldpane.pairing_codes (expires_at);

-- -----------------------------------------------------------------------------
-- Pairing functions
-- -----------------------------------------------------------------------------

-- Create a pairing code for a world. Lazily consumes expired rows with the
-- same hash first; if a LIVE code with the same hash exists, raises
-- unique_violation (23505) and the backend should generate another code.
create or replace function worldpane.create_pairing_code(
  p_world_id   uuid,
  p_code_hash  text,
  p_ttl        interval default interval '10 minutes',
  p_max_uses   integer default 1,
  p_created_by_device_id uuid default null
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_id uuid;
begin
  if p_ttl <= interval '0' then
    raise exception 'ttl must be positive' using errcode = '22023';
  end if;

  update worldpane.pairing_codes
     set consumed_at = now(),
         consumed_reason = 'expired'
   where code_hash = p_code_hash
     and consumed_at is null
     and expires_at <= now();

  insert into worldpane.pairing_codes (world_id, code_hash, expires_at, max_uses, created_by_device_id)
  values (p_world_id, p_code_hash, now() + p_ttl, p_max_uses, p_created_by_device_id)
  returning id into v_id;

  return v_id;
end;
$$;

comment on function worldpane.create_pairing_code(uuid, text, interval, integer, uuid) is
  'Insert a new pairing code (hash only). Raises 23505 if the same code is currently live; regenerate and retry.';

-- Atomically redeem a pairing code and bind the device to the code's world.
-- Never raises for business outcomes; returns (status, world_id) so that the
-- lazy "expired" bookkeeping is committed. The backend maps status -> HTTP and
-- should NOT reveal to the device whether a code was invalid vs. expired.
create or replace function worldpane.redeem_pairing_code(p_code_hash text, p_device_id uuid)
returns worldpane.pairing_result
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_code   worldpane.pairing_codes%rowtype;
  v_device worldpane.devices%rowtype;
begin
  -- Lock the device first (consistent lock order: device, then code).
  select * into v_device
    from worldpane.devices d
   where d.id = p_device_id
   for update;

  if not found then
    return row('device_not_found', null)::worldpane.pairing_result;
  end if;
  if v_device.revoked_at is not null then
    return row('device_revoked', null)::worldpane.pairing_result;
  end if;

  -- Lock the live code row: concurrent redemptions serialize here, so
  -- used_count can never exceed max_uses.
  select * into v_code
    from worldpane.pairing_codes pc
   where pc.code_hash = p_code_hash
     and pc.consumed_at is null
   for update;

  if not found then
    return row('invalid', null)::worldpane.pairing_result;
  end if;

  if v_code.expires_at <= now() then
    update worldpane.pairing_codes
       set consumed_at = now(), consumed_reason = 'expired'
     where id = v_code.id;
    return row('expired', null)::worldpane.pairing_result;
  end if;

  if v_code.used_count >= v_code.max_uses then
    -- Defensive: the check constraint makes this unreachable.
    update worldpane.pairing_codes
       set consumed_at = now(), consumed_reason = 'exhausted'
     where id = v_code.id;
    return row('exhausted', null)::worldpane.pairing_result;
  end if;

  -- Idempotent retry: device already bound to this world -> do not burn a use.
  if v_device.world_id is not distinct from v_code.world_id then
    return row('already_paired', v_code.world_id)::worldpane.pairing_result;
  end if;

  update worldpane.pairing_codes
     set used_count = used_count + 1,
         consumed_at = case when used_count + 1 >= max_uses then now() end,
         consumed_reason = case when used_count + 1 >= max_uses
                                then 'exhausted'::worldpane.pairing_consumed_reason end
   where id = v_code.id;

  -- Clear a primary character from a previous world BEFORE re-binding, so the
  -- device_preferences trigger never sees a cross-world character.
  update worldpane.device_preferences
     set primary_character_id = null
   where device_id = p_device_id
     and primary_character_id is not null;

  update worldpane.devices
     set world_id = v_code.world_id,
         paired_at = now()
   where id = p_device_id;

  insert into worldpane.device_preferences (device_id)
  values (p_device_id)
  on conflict (device_id) do nothing;

  return row('ok', v_code.world_id)::worldpane.pairing_result;
end;
$$;

comment on function worldpane.redeem_pairing_code(text, uuid) is
  'Atomically validate a pairing code (live, not expired, uses left), increment used_count (consuming it at max_uses), bind the device to the world and ensure a device_preferences row. '
  'Returns (status, world_id); status in ok | already_paired | invalid | expired | exhausted | device_not_found | device_revoked.';

-- =============================================================================
-- Row Level Security: enabled everywhere, NO policies => deny-by-default for
-- anon/authenticated. V1 has no user accounts (spec §3); the FastAPI backend
-- uses the service_role key (BYPASSRLS). Add policies only when accounts exist.
-- =============================================================================

alter table worldpane.worlds                  enable row level security;
alter table worldpane.world_revisions         enable row level security;
alter table worldpane.character_profiles      enable row level security;
alter table worldpane.characters              enable row level security;
alter table worldpane.character_relationships enable row level security;
alter table worldpane.daily_plans             enable row level security;
alter table worldpane.events                  enable row level security;
alter table worldpane.event_participants      enable row level security;
alter table worldpane.devices                 enable row level security;
alter table worldpane.device_preferences      enable row level security;
alter table worldpane.pairing_codes           enable row level security;

-- =============================================================================
-- Privileges: service_role only.
-- =============================================================================

revoke all on schema worldpane from public;
revoke all on all tables    in schema worldpane from public;
revoke all on all sequences in schema worldpane from public;
-- Functions are EXECUTE-able by PUBLIC by default; lock them down.
revoke all on all functions in schema worldpane from public;

do $$
declare
  r text;
begin
  -- anon / authenticated exist on Supabase; guard so plain Postgres also works.
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on schema worldpane from %I', r);
      execute format('revoke all on all tables in schema worldpane from %I', r);
      execute format('revoke all on all sequences in schema worldpane from %I', r);
      execute format('revoke all on all functions in schema worldpane from %I', r);
    end if;
  end loop;
end;
$$;

grant usage on schema worldpane to service_role;
grant select, insert, update, delete on all tables in schema worldpane to service_role;
grant usage, select on all sequences in schema worldpane to service_role;
grant execute on all functions in schema worldpane to service_role;

-- Future objects created by the migration owner follow the same rule.
alter default privileges in schema worldpane revoke all on tables    from public;
alter default privileges in schema worldpane revoke all on sequences from public;
alter default privileges in schema worldpane revoke all on functions from public;
alter default privileges in schema worldpane grant select, insert, update, delete on tables to service_role;
alter default privileges in schema worldpane grant usage, select on sequences to service_role;
alter default privileges in schema worldpane grant execute on functions to service_role;
