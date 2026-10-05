#!/bin/sh
# Runs once, when the Postgres volume is first created (docker-entrypoint-initdb.d).
# Recreates the Supabase roles the migrations grant to, then applies migrations + seed.
set -eu
psql_db() { psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" "$@"; }

psql_db -v pw="$WORLDPANE_DB_PASSWORD" <<'SQL'
create role service_role login bypassrls password :'pw';
create role anon nologin;
create role authenticated nologin;
SQL

for f in /supabase/migrations/*.sql; do
    echo "worldpane: applying $f"
    psql_db -f "$f"
done
psql_db -f /supabase/seed.sql
