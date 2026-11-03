#!/usr/bin/env python3
"""Verify a fresh common logical restore in a new DB on the retained clone."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import uuid

operator = runpy.run_path(str(Path(__file__).with_name('unify-arcade-accounts.py')))
kube, resource, sql = (operator[key] for key in ('kube', 'resource', 'sql'))


def digest(pod, database):
    tables = json.loads(sql(pod, "SELECT json_agg(json_build_array(schemaname,tablename) ORDER BY schemaname,tablename) FROM pg_tables WHERE schemaname IN('identity','games','slots','cka');", database))
    result = {}
    for schema, table in tables:
        quoted = '"' + schema.replace('"', '""') + '"."' + table.replace('"', '""') + '"'
        records = sorted(sql(pod, 'SELECT to_jsonb(t)::text FROM ' + quoted + ' t;', database).splitlines())
        result[(schema, table)] = hashlib.sha256('\n'.join(records).encode()).hexdigest()
    result['views'] = sql(pod, "SELECT viewname||':'||definition FROM pg_views WHERE schemaname IN('games','slots') ORDER BY schemaname,viewname;", database)
    result['capabilities'] = sql(pod, "SELECT proname||':'||pg_get_userbyid(proowner)||':'||pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='identity' ORDER BY proname;", database)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', required=True)
    parser.add_argument('--apply', action='store_true', required=True)
    args = parser.parse_args()
    operator['frozen']()
    backup = resource('games', 'backup', args.backup)
    if backup['spec']['cluster']['name'] != 'arcade-postgresql' or backup['status'].get('phase') != 'completed':
        raise RuntimeError('Completed common backup required')
    source = resource('games', 'cluster', 'arcade-postgresql')
    target = resource('games', 'cluster', 'arcade-common-restore')
    if target['status'].get('readyInstances') != 1:
        raise RuntimeError('Resume only the retained common restore clone first')
    source_pod, target_pod = source['status']['currentPrimary'], target['status']['currentPrimary']
    dump = subprocess.run(['kubectl', '--context', 'labprod', '-n', 'games', 'exec', source_pod, '-c', 'postgres', '--', 'pg_dump', '-U', 'postgres', '-Fc', '-d', 'arcade'], capture_output=True)
    if dump.returncode:
        raise RuntimeError('Private dump failed')
    expected = digest(source_pod, 'arcade')
    name = 'arcade_verify_' + uuid.uuid4().hex
    # Only this new uniquely named database is created and dropped. The clone's
    # existing arcade database and every existing PVC remain untouched.
    sql(target_pod, f'CREATE DATABASE {name} OWNER arcade;', 'postgres')
    try:
        restore = subprocess.run(['kubectl', '--context', 'labprod', '-n', 'games', 'exec', '-i', target_pod, '-c', 'postgres', '--', 'pg_restore', '-U', 'postgres', '--exit-on-error', '-d', name], input=dump.stdout, capture_output=True)
        if restore.returncode or digest(target_pod, name) != expected:
            raise RuntimeError('Restored tables, views or capabilities differ')
        print(f'Fresh logical restore verified: {len(expected)-2} tables, both application views and identity capabilities match; no account data logged.')
    finally:
        sql(target_pod, f'DROP DATABASE {name};', 'postgres')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Isolated logical restore refused acceptance; private output withheld. Keep maintenance and inspect through an approved operator session.')
