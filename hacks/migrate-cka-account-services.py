#!/usr/bin/env python3
"""Rehearse or atomically apply the reviewed KubeQuest account migrations.

Uses an immutable private-source commit, a completed common backup and a
restricted transaction under the arcade owner. Never executes reset-progress.sql.
Private logical rehearsal dumps/receipts stay in retained-home backup scope.
"""
import argparse
import calendar
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1] / '.runtime/cka-account-services'
POD = 'arcade-postgresql-1'


def run(argv, **kwargs):
    result = subprocess.run(argv, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError('Command refused; diagnostics withheld')
    return result.stdout


def kubectl(*args, **kwargs):
    return run(['kubectl', '--context', 'labprod', *args], **kwargs)


def sql_payload(source, revision):
    migrations = []
    for name in ['002-progress-reset.sql', '003-account-privacy.sql', '004-email-recovery.sql']:
        body = run(['git', '-C', str(source), 'show', revision + ':db/' + name]).decode()
        migrations.append(re.sub(r'^(?:BEGIN|COMMIT);\s*$', '', body, flags=re.M))
    return ('''BEGIN ISOLATION LEVEL REPEATABLE READ;
SET LOCAL lock_timeout='10s';
SET LOCAL statement_timeout='60s';
LOCK TABLE identity.users,cka.progress IN SHARE MODE;
-- Adopt only the three known legacy CKA objects, inside the same transaction.
DO $ownership$ DECLARE owner_name text; target text; BEGIN
 IF to_regclass('cka.progress_reset_policy') IS NOT NULL THEN
  SELECT pg_get_userbyid(relowner) INTO owner_name FROM pg_class WHERE oid='cka.progress_reset_policy'::regclass;
  IF owner_name NOT IN ('postgres','arcade') THEN RAISE EXCEPTION 'Unexpected CKA policy owner';END IF;
  ALTER TABLE cka.progress_reset_policy OWNER TO arcade;
 END IF;
 FOREACH target IN ARRAY ARRAY['cka.progress_after_reset(jsonb,bigint)','cka.guard_progress_reset()'] LOOP
  IF to_regprocedure(target) IS NOT NULL THEN
   SELECT pg_get_userbyid(proowner) INTO owner_name FROM pg_proc WHERE oid=to_regprocedure(target);
   IF owner_name NOT IN ('postgres','arcade') THEN RAISE EXCEPTION 'Unexpected CKA function owner';END IF;
   EXECUTE 'ALTER FUNCTION '||target||' OWNER TO arcade';
  END IF;
 END LOOP;
END $ownership$;
SET LOCAL ROLE arcade;
CREATE TEMP TABLE cka_release_guard ON COMMIT DROP AS
SELECT (SELECT md5(coalesce(string_agg(row_to_json(u)::text,'' ORDER BY id),'')) FROM identity.users u) AS users,
(SELECT md5(coalesce(string_agg(row_to_json(p)::text,'' ORDER BY owner),'')) FROM cka.progress p) AS progress;
''' + '\n'.join(migrations) + '''
DO $guard$ BEGIN
 IF (SELECT users FROM cka_release_guard) IS DISTINCT FROM (SELECT md5(coalesce(string_agg(row_to_json(u)::text,'' ORDER BY id),'')) FROM identity.users u)
 OR (SELECT progress FROM cka_release_guard) IS DISTINCT FROM (SELECT md5(coalesce(string_agg(row_to_json(p)::text,'' ORDER BY owner),'')) FROM cka.progress p)
 THEN RAISE EXCEPTION 'Account or learning data changed unexpectedly';END IF;
 IF has_function_privilege('cka_app','identity.recover_account(text,text,text)','EXECUTE')
 OR has_function_privilege('cka_app','identity.rotate_recovery(text,text,text[],text)','EXECUTE')
 THEN RAISE EXCEPTION 'Legacy recovery capability is still executable';END IF;
END $guard$;
COMMIT;
''').encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--backup', required=True)
    parser.add_argument('--target', choices=['rehearsal', 'production'], required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch('[a-f0-9]{40}', args.revision):
        parser.error('Use the full immutable source revision')
    payload = sql_payload(args.source, args.revision)
    if not args.apply:
        print('Source reviewed; no mutation. --apply requires a completed backup and rehearsal for production.')
        return
    os.umask(0o077)
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = json.loads(kubectl('-n', 'games', 'get', 'backup', args.backup, '-o', 'json'))
    status = backup.get('status', {})
    if backup['spec'].get('cluster', {}).get('name') != 'arcade-postgresql' or status.get('phase') != 'completed':
        raise RuntimeError('Completed canonical backup required')
    stamp = status.get('stoppedAt', '')
    age = time.time() - calendar.timegm(time.strptime(stamp, '%Y-%m-%dT%H:%M:%SZ'))
    if not 0 <= age < 6 * 3600:
        raise RuntimeError('A backup from this maintenance window is required')
    receipt = ROOT / ('accepted-' + args.revision + '.json')
    if args.target == 'production':
        acceptance = json.loads(receipt.read_text())
        if acceptance.get('revision') != args.revision or acceptance.get('backup') != args.backup or not acceptance.get('rehearsed') or not acceptance.get('legacyOwnershipRehearsed') or not acceptance.get('preservedACL'):
            raise RuntimeError('Matching restored-data rehearsal required')
        kubectl('-n', 'games', 'exec', '-i', POD, '-c', 'postgres', '--', 'psql', '-X', '-U', 'postgres', '-d', 'arcade', '-v', 'ON_ERROR_STOP=1', '-q', input=payload)
        print('Production 002/003/004 committed atomically as arcade; account and progress invariants preserved; no reset.')
        return
    dump = ROOT / ('before-' + args.revision + '-with-acl.dump')
    if not dump.exists():
        raw = kubectl('-n', 'games', 'exec', POD, '-c', 'postgres', '--', 'pg_dump', '-U', 'postgres', '-d', 'arcade', '--format=custom', '--no-owner')
        with dump.open('xb') as output:
            output.write(raw)
    binaries = Path(run(['pg_config', '--bindir']).decode().strip())
    with tempfile.TemporaryDirectory(prefix='cka-restored-account-') as temp:
        directory = Path(temp)
        run([str(binaries / 'initdb'), '-D', str(directory / 'data'), '--auth=trust', '--no-sync'])
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        started = False
        try:
            run([str(binaries / 'pg_ctl'), '-D', str(directory / 'data'), '-l', str(directory / 'postgres.log'), '-o', f'-h 127.0.0.1 -p {port} -k {directory} -F', '-w', 'start'])
            started = True
            connection = ['-h', '127.0.0.1', '-p', str(port)]
            run([str(binaries / 'psql'), *connection, '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', 'CREATE ROLE arcade; CREATE ROLE cka_app; CREATE ROLE postgres;'])
            run([str(binaries / 'createdb'), *connection, '-O', 'arcade', 'cka_rehearsal'])
            run([str(binaries / 'pg_restore'), *connection, '-d', 'cka_rehearsal', '--no-owner', '--role=arcade', '--exit-on-error', str(dump)])
            # pg_restore --no-owner is otherwise blind to the legacy production
            # ownership that must be repaired before SET ROLE arcade.
            owners = json.loads(kubectl('-n', 'games', 'exec', POD, '-c', 'postgres', '--', 'psql', '-X', '-U', 'postgres', '-d', 'arcade', '-Atqc', "SELECT coalesce(json_agg(x),'[]') FROM (SELECT 'TABLE cka.progress_reset_policy' AS target,pg_get_userbyid(relowner) AS owner FROM pg_class WHERE oid=to_regclass('cka.progress_reset_policy') UNION ALL SELECT 'FUNCTION '||oid::regprocedure::text,pg_get_userbyid(proowner) FROM pg_proc WHERE oid IN (to_regprocedure('cka.progress_after_reset(jsonb,bigint)'),to_regprocedure('cka.guard_progress_reset()'))) x"))
            allowed = {'TABLE cka.progress_reset_policy','FUNCTION cka.progress_after_reset(jsonb,bigint)','FUNCTION cka.guard_progress_reset()'}
            for item in owners:
                if item['target'] not in allowed or item['owner'] not in ['postgres','arcade']:
                    raise RuntimeError('Unexpected legacy ownership; review before rehearsal')
                statement = 'ALTER ' + item['target'] + ' OWNER TO ' + item['owner'] + ';'
                run([str(binaries / 'psql'), *connection, '-d', 'cka_rehearsal', '-v', 'ON_ERROR_STOP=1', '-q'], input=statement.encode())
            for _ in range(2):
                run([str(binaries / 'psql'), *connection, '-d', 'cka_rehearsal', '-v', 'ON_ERROR_STOP=1', '-q'], input=payload)
        finally:
            if started:
                run([str(binaries / 'pg_ctl'), '-D', str(directory / 'data'), '-m', 'immediate', '-w', 'stop'])
    receipt.write_text(json.dumps({'revision': args.revision, 'backup': args.backup, 'rehearsed': True, 'legacyOwnershipRehearsed': True, 'preservedACL': True, 'timestamp': int(time.time())}) + '\n')
    print('Actual common logical data restored locally; migration repeated twice with account/progress preservation. Values withheld.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError):
        raise SystemExit('Account migration refused. Check the exact source, completed backup, private rehearsal receipt and owner permissions. No data or credentials displayed.')
