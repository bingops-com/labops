\set ON_ERROR_STOP on
BEGIN;
SELECT pg_advisory_xact_lock(77814264);
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM identity.migrations WHERE id='20261104-unified-accounts') THEN RAISE EXCEPTION 'Normalize canonical accounts first';END IF;
END $$;
CREATE TABLE IF NOT EXISTS identity.profiles(
 account_id text PRIMARY KEY REFERENCES identity.users(id) ON DELETE CASCADE,
 display_name text NOT NULL DEFAULT '' CHECK(length(display_name)<=60),
 bio text NOT NULL DEFAULT '' CHECK(length(bio)<=280),
 location text NOT NULL DEFAULT '' CHECK(length(location)<=80),
 website text NOT NULL DEFAULT '' CHECK(length(website)<=200 AND (website='' OR website ~ '^https?://')),
 contact_email text NOT NULL DEFAULT '' CHECK(length(contact_email)<=254),
 avatar_color text NOT NULL DEFAULT 'blue' CHECK(avatar_color IN('blue','mint','violet','amber')),
 public_profile boolean NOT NULL DEFAULT false,show_badges boolean NOT NULL DEFAULT true,
 theme text NOT NULL DEFAULT 'system' CHECK(theme IN('system','light','dark')),
 reduced_motion boolean NOT NULL DEFAULT false,daily_goal integer NOT NULL DEFAULT 3 CHECK(daily_goal BETWEEN 1 AND 10),
 revision integer NOT NULL DEFAULT 1,updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS identity.external_identities(
 provider text NOT NULL,subject text NOT NULL,account_id text NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
 created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(provider,subject)
);
-- The operator explicitly approved merging the existing directory by username.
-- This allowlist is seeded ONCE; a future public registration cannot claim an
-- unrelated pre-existing SSO identity merely by reserving its username.
CREATE TABLE IF NOT EXISTS identity.migration_sso_claims(
 name_key text PRIMARY KEY,account_id text NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,subject text UNIQUE
);
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM identity.migrations WHERE id='20261104-common-profile') THEN
  INSERT INTO identity.migration_sso_claims(name_key,account_id) SELECT name_key,id FROM identity.users ON CONFLICT DO NOTHING;
  INSERT INTO identity.migrations(id) VALUES('20261104-common-profile');
 END IF;
END $$;
REVOKE ALL ON identity.profiles,identity.external_identities,identity.migration_sso_claims FROM PUBLIC;
CREATE OR REPLACE FUNCTION identity.register_account(p_id text,p_name text,p_password text,p_created bigint) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF p_id !~ '^[a-f0-9]{32}$' OR p_name !~ '^[A-Za-z0-9_-]{3,16}$' OR p_password !~ '^argon2id\$v=19\$m=19456,t=2,p=1\$[A-Za-z0-9+/]+\$[A-Za-z0-9+/]+$' THEN RAISE EXCEPTION 'Invalid common account';END IF;
 INSERT INTO identity.users(id,name,name_key,password,created_at) VALUES(p_id,p_name,lower(p_name),p_password,p_created);
 RETURN p_id;
END $$;
CREATE OR REPLACE FUNCTION identity.resolve_sso(p_subject text,p_name text,p_link text DEFAULT NULL) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE target text; claimed text; existing text; proposed text; previous record; current_progress record;
BEGIN
 IF p_subject !~ '^[a-f0-9]{64}$' OR length(p_name)>100 THEN RAISE EXCEPTION 'Invalid trusted identity';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('labops:'||p_subject,0));
 SELECT account_id INTO target FROM identity.external_identities WHERE provider='labops' AND subject=p_subject;
 IF target IS NOT NULL THEN RETURN target;END IF;
 IF p_link IS NOT NULL THEN
  -- The server already verified both the password and the live SSO session.
  SELECT id INTO target FROM identity.users WHERE id=p_link AND name_key=lower(p_name);
  IF target IS NULL THEN RAISE EXCEPTION 'Accounts do not share the verified username';END IF;
 ELSE
  SELECT account_id,subject INTO target,claimed FROM identity.migration_sso_claims WHERE name_key=lower(p_name) FOR UPDATE;
  IF target IS NOT NULL AND claimed IS NOT NULL AND claimed<>p_subject THEN RAISE EXCEPTION 'SSO link requires account authentication' USING ERRCODE='P0002';END IF;
  IF target IS NULL THEN
   proposed:=CASE WHEN p_name ~ '^[A-Za-z0-9_-]{3,16}$' THEN p_name ELSE 'sso_'||substr(p_subject,1,12) END;
   IF EXISTS(SELECT 1 FROM identity.users WHERE name_key=lower(proposed)) THEN RAISE EXCEPTION 'Sign in to the common account once to link SSO' USING ERRCODE='P0002';END IF;
   target:=replace(gen_random_uuid()::text,'-','');
   INSERT INTO identity.users(id,name,name_key,password,created_at) VALUES(target,proposed,lower(proposed),'',(extract(epoch FROM clock_timestamp())*1000)::bigint);
  END IF;
 END IF;
 INSERT INTO identity.external_identities(provider,subject,account_id) VALUES('labops',p_subject,target);
 UPDATE identity.migration_sso_claims SET subject=p_subject WHERE account_id=target AND (subject IS NULL OR subject=p_subject);
 IF to_regclass('cka.progress') IS NOT NULL THEN
  SELECT * INTO previous FROM cka.progress WHERE owner='sso:'||p_subject FOR UPDATE;
  IF FOUND THEN
   INSERT INTO identity.account_merge_archive(kind,source_key,account_id,payload) VALUES('progress',previous.owner,target,to_jsonb(previous)) ON CONFLICT DO NOTHING;
   SELECT * INTO current_progress FROM cka.progress WHERE owner='account:'||target FOR UPDATE;
   IF FOUND THEN UPDATE cka.progress SET state=identity.merge_progress(current_progress.state,previous.state),revision=greatest(current_progress.revision,previous.revision)+1,updated_at=now() WHERE owner='account:'||target;
   ELSE INSERT INTO cka.progress(owner,account_id,state,revision) VALUES('account:'||target,target,previous.state,previous.revision+1);END IF;
   DELETE FROM cka.progress WHERE owner=previous.owner;
  END IF;
 END IF;
 RETURN target;
END $$;
CREATE OR REPLACE FUNCTION identity.account_profile(p_id text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE result jsonb;
BEGIN
 INSERT INTO identity.profiles(account_id,contact_email) SELECT id,email FROM identity.users WHERE id=p_id ON CONFLICT DO NOTHING;
 SELECT jsonb_build_object('name',u.name,'createdAt',u.created_at,'hasPassword',u.password<>'','recoveryCodes',(SELECT count(*) FROM identity.recovery_codes WHERE user_id=u.id),
 'revision',p.revision,'displayName',p.display_name,'bio',p.bio,'location',p.location,'website',p.website,'contactEmail',p.contact_email,'avatarColor',p.avatar_color,'publicProfile',p.public_profile,'showBadges',p.show_badges,'theme',p.theme,'reducedMotion',p.reduced_motion,'dailyGoal',p.daily_goal)
 INTO result FROM identity.users u JOIN identity.profiles p ON p.account_id=u.id WHERE u.id=p_id;
 RETURN result;
END $$;
CREATE OR REPLACE FUNCTION identity.save_profile(p_id text,p_revision integer,p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM identity.account_profile(p_id);
 UPDATE identity.profiles SET display_name=p->>'displayName',bio=p->>'bio',location=p->>'location',website=p->>'website',contact_email=p->>'contactEmail',avatar_color=p->>'avatarColor',
 public_profile=(p->>'publicProfile')::boolean,show_badges=(p->>'showBadges')::boolean,theme=p->>'theme',reduced_motion=(p->>'reducedMotion')::boolean,daily_goal=(p->>'dailyGoal')::integer,revision=revision+1,updated_at=now()
 WHERE account_id=p_id AND revision=p_revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'Profile changed on another device' USING ERRCODE='40001';END IF;
 RETURN identity.account_profile(p_id);
END $$;
CREATE OR REPLACE FUNCTION identity.public_profile(p_name text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE result jsonb; account text; badges boolean;
BEGIN
 SELECT u.id,p.show_badges,jsonb_build_object('name',u.name,'displayName',p.display_name,'bio',p.bio,'location',p.location,'website',p.website,'avatarColor',p.avatar_color,'showBadges',p.show_badges)
 INTO account,badges,result FROM identity.users u JOIN identity.profiles p ON p.account_id=u.id WHERE u.name_key=lower(p_name) AND p.public_profile;
 IF account IS NULL THEN RETURN NULL;END IF;
 IF badges AND to_regclass('cka.progress') IS NOT NULL THEN
  result:=result||jsonb_build_object('experience',coalesce((SELECT state->'experience' FROM cka.progress WHERE owner='account:'||account),'[]'));
 END IF;
 RETURN result;
END $$;
CREATE OR REPLACE FUNCTION identity.change_password(p_id text,p_old_hash text,p_new_hash text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF p_new_hash !~ '^argon2id\$v=19\$m=19456,t=2,p=1\$[A-Za-z0-9+/]+\$[A-Za-z0-9+/]+$' THEN RAISE EXCEPTION 'Invalid password hash';END IF;
 UPDATE identity.users SET password=p_new_hash WHERE id=p_id AND password=p_old_hash;
 IF NOT FOUND THEN RETURN false;END IF;
 DELETE FROM identity.sessions WHERE user_id=p_id;
 RETURN true;
END $$;
CREATE OR REPLACE FUNCTION identity.rotate_recovery(p_id text,p_password_hash text,p_hashes text[],p_keep text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF cardinality(p_hashes)<>10 OR EXISTS(SELECT 1 FROM unnest(p_hashes) h WHERE h !~ '^[a-f0-9]{64}$') THEN RAISE EXCEPTION 'Invalid recovery codes';END IF;
 UPDATE identity.users SET password=password WHERE id=p_id AND password=p_password_hash;
 IF NOT FOUND THEN RETURN false;END IF;
 DELETE FROM identity.recovery_codes WHERE user_id=p_id;
 INSERT INTO identity.recovery_codes(user_id,token_hash) SELECT p_id,h FROM unnest(p_hashes) h;
 DELETE FROM identity.sessions WHERE user_id=p_id AND token_hash<>p_keep;
 RETURN true;
END $$;
CREATE OR REPLACE FUNCTION identity.recover_account(p_name text,p_code text,p_password text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE target text;
BEGIN
 IF p_password !~ '^argon2id\$v=19\$m=19456,t=2,p=1\$[A-Za-z0-9+/]+\$[A-Za-z0-9+/]+$' THEN RAISE EXCEPTION 'Invalid password hash';END IF;
 SELECT id INTO target FROM identity.users WHERE name_key=lower(p_name) FOR UPDATE;
 IF target IS NULL THEN RETURN false;END IF;
 DELETE FROM identity.recovery_codes WHERE user_id=target AND token_hash=p_code;
 IF NOT FOUND THEN RETURN false;END IF;
 UPDATE identity.users SET password=p_password WHERE id=target;
 DELETE FROM identity.sessions WHERE user_id=target;
 RETURN true;
END $$;
GRANT USAGE ON SCHEMA identity TO cka_app;
-- These RPCs are trusted backend capabilities, never callable by the browser.
REVOKE ALL ON FUNCTION identity.register_account(text,text,text,bigint),identity.resolve_sso(text,text,text),identity.account_profile(text),identity.save_profile(text,integer,jsonb),identity.public_profile(text),identity.change_password(text,text,text),identity.rotate_recovery(text,text,text[],text),identity.recover_account(text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.register_account(text,text,text,bigint),identity.resolve_sso(text,text,text),identity.account_profile(text),identity.save_profile(text,integer,jsonb),identity.public_profile(text),identity.change_password(text,text,text),identity.rotate_recovery(text,text,text[],text),identity.recover_account(text,text,text) TO cka_app;
COMMIT;
