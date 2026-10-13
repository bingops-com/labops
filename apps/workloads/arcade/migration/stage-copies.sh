#!/usr/bin/env bash
# Import disposable, restored copies. Never connect this to source primaries.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
: "${ARCADE_GAMES_RESTORE_SERVICE:?libpq service for the disposable Games restore}"
: "${ARCADE_SLOTS_RESTORE_SERVICE:?libpq service for the disposable Slots restore}"
: "${ARCADE_TARGET_SERVICE:?libpq service for the isolated arcade destination}"
dump_version=$(pg_dump --version)
if [[ ! $dump_version =~ ([0-9]+)\. ]]; then echo 'Cannot identify pg_dump major version' >&2; exit 1; fi
dump_major=${BASH_REMATCH[1]}
source_major=0
for game in games slots; do
  if [[ $game == games ]]; then source_service=$ARCADE_GAMES_RESTORE_SERVICE; else source_service=$ARCADE_SLOTS_RESTORE_SERVICE; fi
  actual=$(PGSERVICE="$source_service" psql -X -At -v ON_ERROR_STOP=1 -c 'SELECT current_database()')
  if [[ $actual != "arcade_${game}_restore" && ! $actual =~ ^arcade_${game}_restore_[0-9a-f]{12}$ ]]; then
    echo 'Refused: source must be a disposable arcade_games_restore or arcade_slots_restore database' >&2
    exit 1
  fi
  server_version=$(PGSERVICE="$source_service" psql -X -At -v ON_ERROR_STOP=1 -c 'SHOW server_version_num')
  if (( server_version / 10000 > source_major )); then source_major=$((server_version / 10000)); fi
  if (( dump_major < server_version / 10000 )); then
    echo 'pg_dump is older than the restored server; install a compatible client before staging' >&2
    exit 1
  fi
done
actual=$(PGSERVICE="$ARCADE_TARGET_SERVICE" psql -X -At -v ON_ERROR_STOP=1 -c 'SELECT current_database()')
if [[ $actual != arcade && ! $actual =~ ^arcade_e2e_[0-9a-f]{12}$ ]]; then echo 'Refused: destination database must be arcade or an isolated rehearsal' >&2; exit 1; fi
target_version=$(PGSERVICE="$ARCADE_TARGET_SERVICE" psql -X -At -v ON_ERROR_STOP=1 -c 'SHOW server_version_num')
if (( target_version / 10000 < source_major )); then echo 'Refused: destination PostgreSQL is older than a restored source' >&2; exit 1; fi
empty=$(PGSERVICE="$ARCADE_TARGET_SERVICE" psql -X -At -v ON_ERROR_STOP=1 -c "SELECT NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname IN ('games', 'slots', 'identity', 'migration'))")
if [[ $empty != t ]]; then
  echo 'Destination already has staging schemas: verify its state; no import attempted' >&2
  exit 1
fi
empty=$(PGSERVICE="$ARCADE_TARGET_SERVICE" psql -X -At -v ON_ERROR_STOP=1 -c "SELECT NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r', 'p', 'v', 'm', 'S'))")
if [[ $empty != t ]]; then echo 'Refused: destination contains application data' >&2; exit 1; fi
for game in games slots; do
  if [[ $game == games ]]; then source_service=$ARCADE_GAMES_RESTORE_SERVICE; else source_service=$ARCADE_SLOTS_RESTORE_SERVICE; fi
  # Fixed internal names only; no dump text replacement or player-data rewriting.
  PGSERVICE="$source_service" psql -X -q -v ON_ERROR_STOP=1 -c "DO \$\$ BEGIN IF to_regnamespace('$game') IS NULL THEN ALTER SCHEMA public RENAME TO $game; END IF; END \$\$;"
done
# Missing COMMIT on a failed dump rolls the destination transaction back.
{
  printf 'BEGIN;\n'
  PGSERVICE="$ARCADE_GAMES_RESTORE_SERVICE" pg_dump --no-owner --no-privileges --schema=games || exit 1
  PGSERVICE="$ARCADE_SLOTS_RESTORE_SERVICE" pg_dump --no-owner --no-privileges --schema=slots || exit 1
  printf 'COMMIT;\n'
} | PGSERVICE="$ARCADE_TARGET_SERVICE" psql -X -q -v ON_ERROR_STOP=1
PGSERVICE="$ARCADE_TARGET_SERVICE" psql -X -q -f prepare.sql
echo 'Restored schemas staged. Import private proofs, then run the aggregate preflight.'
