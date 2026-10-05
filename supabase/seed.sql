-- =============================================================================
-- Worldpane seed (local dev only; `supabase db reset` runs it after migrations)
--
-- One example world with the official default characters 小白 and 小雞毛,
-- their profiles (spec §7–10) and one couple relationship (spec §12).
--
-- !!! Every probability / weight / duration / cooldown marked TBD below is a
-- PLACEHOLDER: spec §34 explicitly leaves these values undecided. They are
-- listed under each config's "_tbd" key (JSON-pointer-ish paths) so the
-- Simulation Core / tooling can flag them. Do NOT treat them as product values.
--
-- Fixed UUIDs keep the seed idempotent and easy to reference in tests.
-- No device / pairing code is seeded: code hashes depend on the backend's
-- WORLDPANE_PAIRING_CODE_SECRET (HMAC), so the backend creates them.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Official template profiles (world_id NULL = shared template)
-- -----------------------------------------------------------------------------

-- 小白: student, Mon–Fri 08:30–17:30 school; ≤1 leave day per calendar month.
insert into worldpane.character_profiles
  (id, world_id, key, name, schedule_config, meal_config, leave_config, event_config)
values (
  '00000000-0000-4000-a000-000000000101',
  null,
  'official.student.v1',
  '學生（官方預設：小白）',
  -- schedule_config (spec §7, §9, §10)
  $json${
    "weekly_blocks": [
      {
        "days": ["mon", "tue", "wed", "thu", "fri"],
        "start": "08:30",
        "end": "17:30",
        "activity": "school",
        "location": "school",
        "scene": "school_classroom",
        "priority": "fixed"
      }
    ],
    "evening_pool_starts_at": "17:30",
    "default_state": { "activity": "idle", "location": "home", "scene": "home_living_room" }
  }$json$::jsonb,
  -- meal_config (spec §8). skip_probability values are TBD placeholders.
  $json${
    "meals": [
      { "key": "breakfast", "window_start": "08:00", "window_end": "11:00", "min_duration_min": 15, "max_duration_min": 20, "skip_probability": 0.10 },
      { "key": "lunch",     "window_start": "11:00", "window_end": "14:00", "min_duration_min": 15, "max_duration_min": 20, "skip_probability": 0.05 },
      { "key": "dinner",    "window_start": "17:00", "window_end": "20:00", "min_duration_min": 15, "max_duration_min": 20, "skip_probability": 0.05 }
    ],
    "min_gap_after_previous_meal_min": 90,
    "gap_applies_after_skipped_meal": false,
    "_tbd": ["/meals/0/skip_probability", "/meals/1/skip_probability", "/meals/2/skip_probability"]
  }$json$::jsonb,
  -- leave_config (spec §7): at most one leave day per calendar month, chosen
  -- uniformly among the month's Mon–Fri. probability is a TBD placeholder.
  $json${
    "mode": "calendar_month",
    "probability_per_period": 0.30,
    "max_per_period": 1,
    "eligible_days": ["mon", "tue", "wed", "thu", "fri"],
    "_tbd": ["/probability_per_period"]
  }$json$::jsonb,
  -- event_config (spec §7 temporary events, §10 evening, §13 holiday context).
  -- All weights / durations / cooldowns are TBD placeholders.
  $json${
    "temporary_events": [
      { "type": "sleeping_in_class", "during_activity": "school", "scene": "school_classroom", "location": "school", "weight": 10, "min_duration_min": 10, "max_duration_min": 30, "max_per_day": 1 },
      { "type": "gaming_in_class",   "during_activity": "school", "scene": "school_classroom", "location": "school", "weight": 10, "min_duration_min": 10, "max_duration_min": 30, "max_per_day": 1 }
    ],
    "leisure_events": [
      { "type": "shower",  "scene": "home_bathroom",    "location": "home", "weight": 30, "min_duration_min": 10, "max_duration_min": 25,  "allowed_time": ["17:30", "23:30"], "allowed_context": ["weekday", "holiday"], "cooldown_min": 720 },
      { "type": "phone",   "scene": "home_living_room", "location": "home", "weight": 30, "min_duration_min": 10, "max_duration_min": 60,  "allowed_time": ["17:30", "23:30"], "allowed_context": ["weekday", "holiday"], "cooldown_min": 30 },
      { "type": "reading", "scene": "home_living_room", "location": "home", "weight": 20, "min_duration_min": 15, "max_duration_min": 60,  "allowed_time": ["17:30", "23:30"], "allowed_context": ["weekday", "holiday"], "cooldown_min": 60 },
      { "type": "gaming",  "scene": "home_living_room", "location": "home", "weight": 20, "min_duration_min": 20, "max_duration_min": 90,  "allowed_time": ["17:30", "23:30"], "allowed_context": ["weekday", "holiday"], "cooldown_min": 60,
        "context_overrides": { "holiday": { "weight": 30, "max_duration_min": 180, "allowed_time": ["09:00", "23:30"] } } }
    ],
    "_tbd": ["/temporary_events/*/weight", "/temporary_events/*/min_duration_min", "/temporary_events/*/max_duration_min",
             "/leisure_events/*/weight", "/leisure_events/*/min_duration_min", "/leisure_events/*/max_duration_min",
             "/leisure_events/*/allowed_time", "/leisure_events/*/cooldown_min", "/leisure_events/*/context_overrides"]
  }$json$::jsonb
)
on conflict (id) do nothing;

-- 小雞毛: office worker, Mon–Fri 08:30–17:30 work; fixed-anchor 14-day leave cycle.
insert into worldpane.character_profiles
  (id, world_id, key, name, schedule_config, meal_config, leave_config, event_config)
values (
  '00000000-0000-4000-a000-000000000102',
  null,
  'official.office_worker.v1',
  '上班族（官方預設：小雞毛）',
  $json${
    "weekly_blocks": [
      {
        "days": ["mon", "tue", "wed", "thu", "fri"],
        "start": "08:30",
        "end": "17:30",
        "activity": "work",
        "location": "office",
        "scene": "office_desk",
        "priority": "fixed"
      }
    ],
    "evening_pool_starts_at": "17:30",
    "default_state": { "activity": "idle", "location": "home", "scene": "home_living_room" }
  }$json$::jsonb,
  $json${
    "meals": [
      { "key": "breakfast", "window_start": "08:00", "window_end": "11:00", "min_duration_min": 15, "max_duration_min": 20, "skip_probability": 0.20 },
      { "key": "lunch",     "window_start": "11:00", "window_end": "14:00", "min_duration_min": 15, "max_duration_min": 20, "skip_probability": 0.05 },
      { "key": "dinner",    "window_start": "17:00", "window_end": "20:00", "min_duration_min": 15, "max_duration_min": 20, "skip_probability": 0.05 }
    ],
    "min_gap_after_previous_meal_min": 90,
    "gap_applies_after_skipped_meal": false,
    "_tbd": ["/meals/0/skip_probability", "/meals/1/skip_probability", "/meals/2/skip_probability"]
  }$json$::jsonb,
  -- Fixed 14-day cycles counted from cycle_anchor_date; the anchor never moves
  -- because of an actual leave day (spec §7). probability is TBD.
  -- cycle_anchor_date here equals the seeded world's simulation_start_date.
  $json${
    "mode": "fixed_cycle",
    "cycle_days": 14,
    "cycle_anchor_date": "2026-10-05",
    "probability_per_period": 0.30,
    "max_per_period": 1,
    "eligible_days": ["mon", "tue", "wed", "thu", "fri"],
    "_tbd": ["/probability_per_period"]
  }$json$::jsonb,
  $json${
    "temporary_events": [
      { "type": "slacking", "during_activity": "work", "scene": "office_desk", "location": "office", "weight": 10, "min_duration_min": 10, "max_duration_min": 30, "max_per_day": 2 }
    ],
    "leisure_events": [
      { "type": "shower",  "scene": "home_bathroom",    "location": "home", "weight": 30, "min_duration_min": 10, "max_duration_min": 25, "allowed_time": ["17:30", "23:30"], "allowed_context": ["weekday", "holiday"], "cooldown_min": 720 },
      { "type": "phone",   "scene": "home_living_room", "location": "home", "weight": 30, "min_duration_min": 10, "max_duration_min": 60, "allowed_time": ["17:30", "23:30"], "allowed_context": ["weekday", "holiday"], "cooldown_min": 30 },
      { "type": "reading", "scene": "home_living_room", "location": "home", "weight": 20, "min_duration_min": 15, "max_duration_min": 60, "allowed_time": ["17:30", "23:30"], "allowed_context": ["weekday", "holiday"], "cooldown_min": 60 },
      { "type": "gaming",  "scene": "home_living_room", "location": "home", "weight": 15, "min_duration_min": 20, "max_duration_min": 90, "allowed_time": ["17:30", "23:30"], "allowed_context": ["weekday", "holiday"], "cooldown_min": 60 }
    ],
    "_tbd": ["/temporary_events/*/weight", "/temporary_events/*/min_duration_min", "/temporary_events/*/max_duration_min",
             "/leisure_events/*/weight", "/leisure_events/*/min_duration_min", "/leisure_events/*/max_duration_min",
             "/leisure_events/*/allowed_time", "/leisure_events/*/cooldown_min"]
  }$json$::jsonb
)
on conflict (id) do nothing;

-- -----------------------------------------------------------------------------
-- Example world + shared / group event rules (spec §11–13). Values are TBD.
-- -----------------------------------------------------------------------------

insert into worldpane.worlds
  (id, name, timezone, simulation_version, simulation_start_date, shared_event_config)
values (
  '00000000-0000-4000-a000-000000000001',
  '小白與小雞毛的世界',
  'Asia/Taipei',
  1,
  date '2026-10-05',
  $json${
    "shared_events": [
      { "type": "movie",        "scene": "home_living_room", "location": "home", "min_participants": 2, "max_participants": 2, "relationship_required": "couple",
        "weight": 20, "min_duration_min": 90, "max_duration_min": 150, "allowed_time": ["19:00", "23:30"], "allowed_context": ["weekday", "holiday"], "cooldown_min": 2880 },
      { "type": "basketball",   "scene": "park_court", "location": "park", "min_participants": 2, "max_participants": 5,
        "weight": 10, "min_duration_min": 60, "max_duration_min": 120, "allowed_time": ["09:00", "18:00"], "allowed_context": ["holiday"], "cooldown_min": 4320 },
      { "type": "group_dinner", "scene": "restaurant", "location": "restaurant", "min_participants": 2, "max_participants": 8,
        "weight": 10, "min_duration_min": 60, "max_duration_min": 120, "allowed_time": ["17:30", "21:00"], "allowed_context": ["holiday"], "cooldown_min": 4320,
        "replaces_meal": "dinner" }
    ],
    "_tbd": ["/shared_events/*/weight", "/shared_events/*/min_duration_min", "/shared_events/*/max_duration_min",
             "/shared_events/*/allowed_time", "/shared_events/*/cooldown_min", "/shared_events/2/replaces_meal"]
  }$json$::jsonb
)
on conflict (id) do nothing;

insert into worldpane.characters (id, world_id, appearance_key, display_name, profile_id, sort_order)
values
  ('00000000-0000-4000-a000-000000000011', '00000000-0000-4000-a000-000000000001', 'xiaobai',   '小白',   '00000000-0000-4000-a000-000000000101', 0),
  ('00000000-0000-4000-a000-000000000012', '00000000-0000-4000-a000-000000000001', 'xiaojimao', '小雞毛', '00000000-0000-4000-a000-000000000102', 1)
on conflict (id) do nothing;

insert into worldpane.character_relationships
  (id, world_id, character_a_id, character_b_id, relationship_type)
values (
  '00000000-0000-4000-a000-000000000021',
  '00000000-0000-4000-a000-000000000001',
  '00000000-0000-4000-a000-000000000011',
  '00000000-0000-4000-a000-000000000012',
  'couple'
)
on conflict do nothing;
