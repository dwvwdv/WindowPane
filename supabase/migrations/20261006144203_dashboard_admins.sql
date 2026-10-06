-- =============================================================================
-- Dashboard admins: Supabase Auth accounts allowed to use /dashboard.
--
-- Signing in with Supabase Auth only proves who someone is; an account can use the
-- dashboard only when its auth.users id is listed here. Register one with:
--
--   insert into worldpane.admins (user_id, display_name)
--   select id, 'your name' from auth.users where email = 'you@example.com';
--
-- The backend (service role) is the only reader; RLS is on with no policies.
-- =============================================================================

create table worldpane.admins (
  -- auth.users.id. The foreign key is added below only where Supabase Auth exists, so the
  -- bundled Postgres (docker compose --profile local-db) and CI can apply this migration too.
  user_id      uuid primary key,
  display_name text not null check (char_length(btrim(display_name)) between 1 and 80),
  created_at   timestamptz not null default now()
);

comment on table worldpane.admins is
  'Supabase Auth users allowed to use the WorldPane dashboard (/dashboard, /api/v1/admin).';

do $$
begin
  if to_regclass('auth.users') is not null then
    alter table worldpane.admins
      add constraint admins_user_fk foreign key (user_id) references auth.users (id) on delete cascade;
  end if;
end;
$$;

alter table worldpane.admins enable row level security;

revoke all on worldpane.admins from public;
do $$
declare
  r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on worldpane.admins from %I', r);
    end if;
  end loop;
end;
$$;
grant select, insert, update, delete on worldpane.admins to service_role;
