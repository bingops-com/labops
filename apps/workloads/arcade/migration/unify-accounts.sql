\set ON_ERROR_STOP on
-- Authorized policy: keep the earliest (created_at, id COLLATE "C") account.
-- Run on the common database after graceful Games/Slots maintenance and backup.
BEGIN;
SET LOCAL lock_timeout='15s';
SELECT pg_advisory_xact_lock(77814264);
CREATE TABLE IF NOT EXISTS identity.migrations(id text PRIMARY KEY,applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS identity.account_merge_archive(
 kind text NOT NULL, source_key text NOT NULL, account_id text NOT NULL,
 payload jsonb NOT NULL, archived_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(kind,source_key)
);
REVOKE ALL ON identity.account_merge_archive FROM PUBLIC;
CREATE TABLE IF NOT EXISTS identity.account_aliases(
 old_id text PRIMARY KEY,account_id text NOT NULL REFERENCES identity.users(id),created_at timestamptz NOT NULL DEFAULT now()
);
\ir progress-functions.sql
DO $migration$
DECLARE refs record; winner record; progress record; combined jsonb; rev integer; columns text; definition record; app text; expected bigint;
BEGIN
 IF EXISTS(SELECT 1 FROM identity.migrations WHERE id='20261104-unified-accounts') THEN RETURN; END IF;
 IF NOT EXISTS(SELECT 1 FROM identity.schema_version WHERE version=1) THEN RAISE EXCEPTION 'Expected compatible common identities';END IF;
 LOCK TABLE identity.users,identity.sessions,identity.account_links IN ACCESS EXCLUSIVE MODE;
 CREATE TEMP TABLE unify_map ON COMMIT DROP AS
 SELECT id old_id,first_value(id) OVER(PARTITION BY lower(name) ORDER BY created_at,id COLLATE "C") account_id,lower(name) name_key
 FROM identity.users;
 SELECT count(DISTINCT account_id) INTO expected FROM unify_map;
 CREATE TEMP TABLE unify_profiles ON COMMIT DROP AS
 SELECT DISTINCT ON(m.account_id) m.account_id,
  (SELECT to_jsonb(u) FROM identity.users u JOIN unify_map x ON u.id=x.old_id WHERE x.account_id=m.account_id ORDER BY (u.origin='games') DESC,u.created_at,u.id COLLATE "C" LIMIT 1) games,
  (SELECT to_jsonb(u) FROM identity.users u JOIN unify_map x ON u.id=x.old_id WHERE x.account_id=m.account_id ORDER BY (u.origin='slots') DESC,u.created_at,u.id COLLATE "C" LIMIT 1) slots
 FROM unify_map m;
 INSERT INTO identity.account_merge_archive(kind,source_key,account_id,payload)
 SELECT 'user',u.id,m.account_id,to_jsonb(u) FROM identity.users u JOIN unify_map m ON m.old_id=u.id
 WHERE EXISTS(SELECT 1 FROM unify_map x WHERE x.account_id=m.account_id AND x.old_id<>x.account_id)
 ON CONFLICT DO NOTHING;
 INSERT INTO identity.account_aliases(old_id,account_id)
 SELECT old_id,account_id FROM unify_map WHERE old_id<>account_id ON CONFLICT(old_id) DO UPDATE SET account_id=excluded.account_id;
 IF to_regclass('cka.progress') IS NOT NULL THEN
  LOCK TABLE cka.progress IN ACCESS EXCLUSIVE MODE;
  FOR winner IN SELECT DISTINCT account_id FROM unify_map WHERE old_id<>account_id LOOP
   combined:=NULL;rev:=0;
   FOR progress IN SELECT p.* FROM cka.progress p JOIN unify_map m ON m.old_id=p.account_id WHERE m.account_id=winner.account_id ORDER BY (p.account_id=winner.account_id) DESC,p.updated_at LOOP
    INSERT INTO identity.account_merge_archive(kind,source_key,account_id,payload) VALUES('progress',progress.owner,winner.account_id,to_jsonb(progress)) ON CONFLICT DO NOTHING;
    combined:=CASE WHEN combined IS NULL THEN progress.state ELSE identity.merge_progress(combined,progress.state) END;
    rev:=greatest(rev,progress.revision);
   END LOOP;
   DELETE FROM cka.progress p USING unify_map m WHERE p.account_id=m.old_id AND m.account_id=winner.account_id;
   IF combined IS NOT NULL THEN INSERT INTO cka.progress(owner,account_id,state,revision) VALUES('account:'||winner.account_id,winner.account_id,combined,rev+1); END IF;
  END LOOP;
 END IF;
 -- Fail atomically for an unknown composite reference, rather than dropping data.
 IF EXISTS(SELECT 1 FROM pg_constraint WHERE confrelid='identity.users'::regclass AND contype='f' AND cardinality(conkey)<>1) THEN RAISE EXCEPTION 'Composite account reference needs an explicit adapter';END IF;
 -- Recovery credentials from a discarded account must not unlock the winner.
 INSERT INTO identity.account_merge_archive(kind,source_key,account_id,payload)
 SELECT 'recovery',c.user_id||':'||c.token_hash,m.account_id,to_jsonb(c) FROM identity.recovery_codes c JOIN unify_map m ON m.old_id=c.user_id WHERE m.old_id<>m.account_id ON CONFLICT DO NOTHING;
 DELETE FROM identity.recovery_codes c USING unify_map m WHERE c.user_id=m.old_id AND m.old_id<>m.account_id;
 DELETE FROM games.password_resets c USING unify_map m WHERE c.user_id=m.old_id AND m.old_id<>m.account_id;
 DELETE FROM games.email_checks c USING unify_map m WHERE c.user_id=m.old_id AND m.old_id<>m.account_id;
 FOR refs IN
  SELECT n.nspname,c.relname,a.attname FROM pg_constraint fk JOIN pg_class c ON c.oid=fk.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=fk.conkey[1]
  WHERE fk.confrelid='identity.users'::regclass AND fk.contype='f' AND NOT(n.nspname='cka' AND c.relname='progress')
 LOOP
  EXECUTE format('UPDATE %I.%I t SET %I=m.account_id FROM unify_map m WHERE t.%I=m.old_id AND m.old_id<>m.account_id',refs.nspname,refs.relname,refs.attname,refs.attname);
 END LOOP;
 -- Text references in historical reports/audit are exact IDs, never substring replacements.
 UPDATE games.reports r SET reporter=m.account_id FROM unify_map m WHERE r.reporter=m.old_id AND m.old_id<>m.account_id;
 UPDATE games.reports r SET target=m.account_id FROM unify_map m WHERE r.target=m.old_id AND m.old_id<>m.account_id;
 UPDATE games.admin_audit a SET target=m.account_id FROM unify_map m WHERE a.target=m.old_id AND m.old_id<>m.account_id;
 DELETE FROM identity.users u USING unify_map m WHERE u.id=m.old_id AND m.old_id<>m.account_id;
 UPDATE identity.users u SET
  avatar=p.games->>'avatar',streak=(p.games->>'streak')::integer,streak_best=(p.games->>'streak_best')::integer,last_day=(p.games->>'last_day')::integer,
  credits=(p.games->>'credits')::integer,name_fx=p.games->>'name_fx',email=p.games->>'email',credits_day=(p.games->>'credits_day')::integer,credits_today=(p.games->>'credits_today')::integer,email_checked=(p.games->>'email_checked')::boolean,
  wallet=p.slots->'wallet',score=(p.slots->>'score')::bigint,best_mult=(p.slots->>'best_mult')::double precision,best_game=p.slots->>'best_game',wagered=(p.slots->>'wagered')::bigint,rounds=(p.slots->>'rounds')::bigint,stake=(p.slots->>'stake')::bigint,
  origin='shared',name_key=lower(u.name)
 FROM unify_profiles p WHERE p.account_id=u.id;
 -- Credential policy is the winning account's password, without legacy alternatives.
 DELETE FROM identity.sessions;
 IF (SELECT count(*) FROM identity.users)<>expected OR EXISTS(SELECT lower(name) FROM identity.users GROUP BY lower(name) HAVING count(*)>1) THEN RAISE EXCEPTION 'Canonical identity conservation failed';END IF;
 ALTER TABLE identity.users ADD CONSTRAINT users_canonical_name CHECK(name_key=lower(name));
 ALTER TABLE identity.users ADD CONSTRAINT users_shared_only CHECK(origin='shared');
 -- Source labels are migration audit information, never a login namespace.
 ALTER TABLE identity.account_links DROP CONSTRAINT IF EXISTS account_links_source_app_check;
 ALTER TABLE identity.account_links ADD CONSTRAINT account_links_source_format CHECK(source_app ~ '^[a-z][a-z0-9-]{0,31}$');
 SELECT string_agg(format('u.%I',attname),', ' ORDER BY attnum) INTO columns FROM pg_attribute WHERE attrelid='identity.users'::regclass AND attnum>0 AND NOT attisdropped;
 FOREACH app IN ARRAY ARRAY['games','slots'] LOOP
  EXECUTE format('CREATE OR REPLACE VIEW %I.users AS SELECT %s FROM identity.users u WITH LOCAL CHECK OPTION',app,columns);
 END LOOP;
 INSERT INTO identity.migrations(id) VALUES('20261104-unified-accounts');
END $migration$;
-- Rewrite exact JSON ID references in retained room/season state.
CREATE OR REPLACE FUNCTION identity.rewrite_account_ids(value jsonb) RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path=pg_catalog AS $$
DECLARE result jsonb; item record; replacement text;
BEGIN
 CASE jsonb_typeof(value)
 WHEN 'string' THEN SELECT account_id INTO replacement FROM identity.account_aliases WHERE old_id=value#>>'{}';RETURN CASE WHEN replacement IS NULL THEN value ELSE to_jsonb(replacement) END;
 WHEN 'array' THEN SELECT coalesce(jsonb_agg(identity.rewrite_account_ids(v)),'[]') INTO result FROM jsonb_array_elements(value) v;RETURN result;
 WHEN 'object' THEN
  result:='{}';FOR item IN SELECT * FROM jsonb_each(value) LOOP
   SELECT account_id INTO replacement FROM identity.account_aliases WHERE old_id=item.key;
   result:=result||jsonb_build_object(coalesce(replacement,item.key),identity.rewrite_account_ids(item.value));
  END LOOP;RETURN result;
 ELSE RETURN value;
 END CASE;
END $$;
REVOKE ALL ON FUNCTION identity.rewrite_account_ids(jsonb) FROM PUBLIC;
UPDATE games.rooms SET state=identity.rewrite_account_ids(state) WHERE state IS DISTINCT FROM identity.rewrite_account_ids(state);
UPDATE slots.seasons SET podium=identity.rewrite_account_ids(podium) WHERE podium IS NOT NULL AND podium IS DISTINCT FROM identity.rewrite_account_ids(podium);
COMMIT;
