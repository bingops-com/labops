\set ON_ERROR_STOP on
-- Aggregate-only, no pseudo, hash, cookie or other account data in output.
BEGIN READ ONLY;
SELECT (SELECT COUNT(*) FROM games.users) AS games_accounts,
       (SELECT COUNT(*) FROM slots.users) AS slots_accounts,
       COUNT(*) AS overlapping_names,
       COUNT(*) FILTER (WHERE NOT EXISTS (
           SELECT 1 FROM migration.links l
           JOIN games.sessions gs ON gs.token_hash = l.games_token_hash
           JOIN slots.sessions ss ON ss.token_hash = l.slots_token_hash
           WHERE l.name_key = g.name_key AND gs.user_id = g.id AND ss.user_id = s.id
           AND gs.expires_at > (EXTRACT(EPOCH FROM now()) * 1000)::BIGINT
           AND ss.expires_at > (EXTRACT(EPOCH FROM now()) * 1000)::BIGINT
       )) AS missing_valid_proofs
FROM games.users g JOIN slots.users s USING (name_key);
COMMIT;
