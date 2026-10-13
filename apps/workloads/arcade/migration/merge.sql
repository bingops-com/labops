\set ON_ERROR_STOP on
-- Only an isolated destination imported from stopped/snapshotted sources.
-- Source databases and their historical backups are never touched.
BEGIN;
SET LOCAL lock_timeout = '10s';
SELECT pg_advisory_xact_lock(77814264);
DO $merge$
DECLARE
    old_count BIGINT;
    slots_count BIGINT;
    duplicate_count BIGINT;
    constraint_name TEXT;
BEGIN
    IF to_regclass('identity.schema_version') IS NOT NULL THEN
        IF (SELECT MAX(version) FROM identity.schema_version) IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION 'Unsupported shared account schema';
        END IF;
        RETURN; -- Never revoke sessions or re-import accounts on a retry.
    END IF;
    IF (SELECT MAX(version) FROM games.schema_version) IS DISTINCT FROM 8
        OR (SELECT MAX(version) FROM slots.schema_migrations) IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'Expected Games schema 8 and Slots schema 1';
    END IF;
    LOCK TABLE games.users, slots.users, games.sessions, slots.sessions IN ACCESS EXCLUSIVE MODE;
    IF EXISTS (SELECT 1 FROM games.users WHERE name_key <> lower(name) OR name !~ '^[A-Za-z0-9_-]{3,16}$')
        OR EXISTS (SELECT 1 FROM slots.users WHERE name_key <> lower(name) OR name !~ '^[A-Za-z0-9_-]{3,16}$') THEN
        RAISE EXCEPTION 'Unexpected account name format';
    END IF;
    IF EXISTS (SELECT 1 FROM games.users g JOIN slots.users s USING (id) WHERE g.name_key <> s.name_key) THEN
        RAISE EXCEPTION 'Account ID collision requires a separately reviewed migration';
    END IF;
    IF EXISTS (
        SELECT 1 FROM games.users g JOIN slots.users s USING (name_key)
        WHERE NOT EXISTS (
            SELECT 1 FROM migration.links l
            JOIN games.sessions gs ON gs.token_hash = l.games_token_hash
            JOIN slots.sessions ss ON ss.token_hash = l.slots_token_hash
            WHERE l.name_key = g.name_key AND gs.user_id = g.id AND ss.user_id = s.id
            AND gs.expires_at > (EXTRACT(EPOCH FROM now()) * 1000)::BIGINT
            AND ss.expires_at > (EXTRACT(EPOCH FROM now()) * 1000)::BIGINT
        )
    ) THEN
        RAISE EXCEPTION 'Overlapping accounts require proof of both passwords; no accounts changed';
    END IF;
    SELECT COUNT(*) INTO old_count FROM games.users;
    SELECT COUNT(*) INTO slots_count FROM slots.users;
    SELECT COUNT(*) INTO duplicate_count FROM games.users JOIN slots.users USING (name_key);
    CREATE TEMP TABLE arcade_games_ids ON COMMIT DROP AS SELECT id FROM games.users;

    CREATE SCHEMA identity;
    REVOKE ALL ON SCHEMA identity FROM PUBLIC;
    ALTER TABLE games.users SET SCHEMA identity;
    ALTER TABLE games.sessions SET SCHEMA identity;
    ALTER TABLE games.recovery_codes SET SCHEMA identity;
    -- Existing SQL updates only the fields owned by that game. Wallets and
    -- Games shop credits are independent; neither balance is added to the other.
    ALTER TABLE identity.users
        ADD COLUMN wallet JSONB NOT NULL DEFAULT '{"stake":1000000,"loot":0,"debt":0,"wagered":0,"won":0,"rounds":0,"rebuys":0,"best":null,"bj":null,"mines":null,"crash":null}',
        ADD COLUMN score BIGINT NOT NULL DEFAULT 0,
        ADD COLUMN best_mult DOUBLE PRECISION NOT NULL DEFAULT 0,
        ADD COLUMN best_game TEXT NOT NULL DEFAULT '',
        ADD COLUMN wagered BIGINT NOT NULL DEFAULT 0,
        ADD COLUMN rounds BIGINT NOT NULL DEFAULT 0,
        ADD COLUMN stake BIGINT NOT NULL DEFAULT 1000000;
    CREATE INDEX users_score ON identity.users (score DESC) WHERE rounds > 0;
    CREATE INDEX users_best ON identity.users (best_mult DESC) WHERE rounds > 0;
    CREATE INDEX users_wagered ON identity.users (wagered DESC) WHERE rounds > 0;

    INSERT INTO identity.users (id, name, name_key, password, created_at, wallet, score, best_mult, best_game, wagered, rounds, stake)
    SELECT s.id, s.name, s.name_key, s.password, s.created_at, s.wallet, s.score, s.best_mult, s.best_game, s.wagered, s.rounds, s.stake
    FROM slots.users s WHERE NOT EXISTS (SELECT 1 FROM identity.users a WHERE a.name_key = s.name_key);
    UPDATE identity.users a SET wallet = s.wallet, score = s.score, best_mult = s.best_mult,
        best_game = s.best_game, wagered = s.wagered, rounds = s.rounds, stake = s.stake
    FROM slots.users s WHERE s.name_key = a.name_key;

    CREATE TABLE identity.account_links (
        source_app TEXT NOT NULL CHECK (source_app IN ('games', 'slots')),
        source_user_id TEXT NOT NULL,
        account_id TEXT NOT NULL REFERENCES identity.users(id),
        PRIMARY KEY (source_app, source_user_id)
    );
    INSERT INTO identity.account_links SELECT 'games', id, id FROM arcade_games_ids;
    INSERT INTO identity.account_links SELECT 'slots', s.id, a.id FROM slots.users s JOIN identity.users a USING (name_key);

    FOR constraint_name IN SELECT conname FROM pg_constraint
        WHERE conrelid = 'slots.game_stats'::regclass AND confrelid = 'slots.users'::regclass AND contype = 'f'
    LOOP
        EXECUTE format('ALTER TABLE slots.game_stats DROP CONSTRAINT %I', constraint_name);
    END LOOP;
    UPDATE slots.game_stats t SET user_id = l.account_id FROM identity.account_links l
        WHERE l.source_app = 'slots' AND l.source_user_id = t.user_id;
    ALTER TABLE slots.game_stats ADD CONSTRAINT game_stats_account_fk FOREIGN KEY (user_id) REFERENCES identity.users(id) ON DELETE CASCADE;
    ALTER TABLE slots.users SET SCHEMA migration;
    ALTER TABLE slots.sessions SET SCHEMA migration;
    -- Reauthentication is mandatory at cutover. No bearer cookies are imported.
    DELETE FROM identity.sessions;
    DELETE FROM migration.sessions;
    -- Remove obsolete Slots password hashes only on this disposable destination.
    -- Sources/backups retain the pre-migration data for rollback.
    ALTER TABLE migration.users DROP COLUMN password;
    DELETE FROM migration.links;
    IF (SELECT COUNT(*) FROM identity.users) <> old_count + slots_count - duplicate_count THEN
        RAISE EXCEPTION 'Account conservation check failed';
    END IF;
    CREATE TABLE identity.schema_version (version INTEGER PRIMARY KEY CHECK (version = 1));
    INSERT INTO identity.schema_version VALUES (1);
END
$merge$;
COMMIT;
