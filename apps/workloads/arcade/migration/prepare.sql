\set ON_ERROR_STOP on
-- On the isolated destination ONLY, after importing the games/slots schemas.
CREATE SCHEMA IF NOT EXISTS migration;
REVOKE ALL ON SCHEMA migration FROM PUBLIC;
CREATE TABLE IF NOT EXISTS migration.links (
    name_key TEXT PRIMARY KEY CHECK (name_key ~ '^[a-z0-9_-]{3,16}$'),
    games_token_hash TEXT NOT NULL CHECK (games_token_hash ~ '^[0-9a-f]{64}$'),
    slots_token_hash TEXT NOT NULL CHECK (slots_token_hash ~ '^[0-9a-f]{64}$')
);
