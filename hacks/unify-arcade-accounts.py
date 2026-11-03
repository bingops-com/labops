#!/usr/bin/env python3
"""Guarded canonical-account upgrade; comparisons never print account records."""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'apps/workloads/arcade/migration'
GAMES_FIELDS = 'avatar streak streak_best last_day credits name_fx email credits_day credits_today email_checked'.split()
SLOTS_FIELDS = 'wallet score best_mult best_game wagered rounds stake'.split()


def command(args, data=None):
    result = subprocess.run(args, input=data, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Operator command failed; private database output withheld')
    return result.stdout


def kube(*args, data=None):
    return command(['kubectl', '--context', 'labprod', *args], data)


def resource(namespace, kind, name):
    return json.loads(kube('-n', namespace, 'get', kind, name, '-o', 'json'))


def sql(pod, statement, database='arcade'):
    return kube('-n', 'games', 'exec', '-i', pod, '-c', 'postgres', '--',
                'psql', '-X', '-At', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres',
                '-d', database, data=statement)


def rows(pod, statement):
    return [json.loads(line) for line in sql(pod, statement).splitlines() if line]


def table(pod, schema, name):
    # Names originate from pg_catalog, and identifiers are quoted safely.
    quote = lambda value: '"' + value.replace('"', '""') + '"'
    return rows(pod, f'SELECT row_to_json(t) FROM {quote(schema)}.{quote(name)} t;')


def frozen():
    for namespace, name in [('games', 'games'), ('slots', 'slots'), ('cka', 'cka')]:
        deployment = resource(namespace, 'deployment', name)
        if deployment['spec'].get('replicas', 1) or deployment['status'].get('replicas', 0):
            raise RuntimeError('Games, Slots and CKA web must be gracefully frozen in GitOps')
        pods = json.loads(kube('-n', namespace, 'get', 'pods', '-l',
                              ('app=cka' if name == 'cka' else 'app.kubernetes.io/name=' + name), '-o', 'json'))
        if any(p['status'].get('phase') not in ('Succeeded', 'Failed') for p in pods['items']):
            raise RuntimeError('A web writer Pod still exists')


def snapshot(pod):
    users = table(pod, 'identity', 'users')
    groups = {}
    for user in sorted(users, key=lambda u: (u['created_at'], u['id'].encode())):
        groups.setdefault(user['name'].lower(), []).append(user)
    mapping = {user['id']: group[0]['id'] for group in groups.values() for user in group}
    expected = {}
    for group in groups.values():
        winner = dict(group[0])
        for app, fields in [('games', GAMES_FIELDS), ('slots', SLOTS_FIELDS)]:
            source = next((user for user in group if user['origin'] == app), group[0])
            winner.update({field: source[field] for field in fields})
        winner.update(origin='shared', name_key=winner['name'].lower())
        expected[winner['id']] = winner
    references = rows(pod, """SELECT json_build_object('schema',n.nspname,'table',c.relname,'column',a.attname)
      FROM pg_constraint f JOIN pg_class c ON c.oid=f.conrelid
      JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=f.conkey[1]
      WHERE f.contype='f' AND f.confrelid='identity.users'::regclass;""")
    tables = {}
    for ref in references:
        key = (ref['schema'], ref['table'])
        tables.setdefault(key, {'columns': [], 'rows': table(pod, *key)})['columns'].append(ref['column'])
    for key, columns in [(('games', 'reports'), ['reporter', 'target']),
                         (('games', 'admin_audit'), ['target']),
                         (('games', 'rooms'), ['state']), (('slots', 'seasons'), ['podium'])]:
        tables[key] = {'columns': columns, 'rows': table(pod, *key)}
    return users, expected, mapping, tables


def rewrite(value, mapping):
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [rewrite(item, mapping) for item in value]
    if isinstance(value, dict):
        return {mapping.get(key, key): rewrite(item, mapping) for key, item in value.items()}
    return value


def canonical(records):
    return sorted(json.dumps(row, sort_keys=True, separators=(',', ':')) for row in records)


def verify(pod, before):
    original, expected, mapping, tables = before
    actual = {user['id']: user for user in table(pod, 'identity', 'users')}
    if actual != expected:
        raise RuntimeError('Canonical credentials or service balances differ; values withheld')
    archived = {row['source_key']: row['payload'] for row in table(pod, 'identity', 'account_merge_archive') if row['kind'] == 'user'}
    for user in original:
        if sum(target == mapping[user['id']] for target in mapping.values()) > 1 and archived.get(user['id']) != user:
            raise RuntimeError('Original duplicate-account archive is incomplete')
    for (schema, name), data in tables.items():
        if (schema, name) == ('identity', 'sessions') and any(old != target for old, target in mapping.items()):
            if table(pod, schema, name):
                raise RuntimeError('Password sessions were not revoked')
            continue
        if (schema, name) == ('cka', 'progress'):
            # The merge SQL and synthetic integration test verify unions. Every
            # modified real record must additionally have an exact archive.
            archive = {r['source_key']: r['payload'] for r in table(pod, 'identity', 'account_merge_archive') if r['kind'] == 'progress'}
            current = {r['owner']: r for r in table(pod, schema, name)}
            for row in data['rows']:
                account = row['account_id']
                duplicate = account and sum(target == mapping[account] for target in mapping.values()) > 1
                if duplicate and archive.get(row['owner']) != row:
                    raise RuntimeError('Original study progress archive differs')
                if not duplicate and current.get(row['owner']) != row:
                    raise RuntimeError('Unrelated study progress changed')
            continue
        wanted = []
        for row in data['rows']:
            losing = any(row.get(column) in mapping and mapping[row[column]] != row[column] for column in data['columns'] if isinstance(row.get(column), str))
            if losing and (schema, name) in [('identity', 'recovery_codes'), ('games', 'password_resets'), ('games', 'email_checks')]:
                continue
            row = dict(row)
            for column in data['columns']:
                row[column] = rewrite(row[column], mapping)
            wanted.append(row)
        if canonical(wanted) != canonical(table(pod, schema, name)):
            raise RuntimeError('Referenced service history differs; values withheld')
    for app in ('games', 'slots'):
        if canonical(list(actual.values())) != canonical(table(pod, app, 'users')):
            raise RuntimeError('Application still exposes a separate account directory')
    owners = rows(pod, "SELECT json_build_object('owner',pg_get_userbyid(proowner),'secure',prosecdef) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='identity' AND p.proname IN('account_profile','save_profile','resolve_sso','public_profile','register_account','change_password','rotate_recovery','recover_account');")
    if len(owners) != 8 or any(row != {'owner': 'arcade', 'secure': True} for row in owners):
        raise RuntimeError('Profile capabilities have unexpected owners')
    print(f'Verified {len(original)} identities → {len(actual)} common accounts; earliest credentials, separate balances, references, archives and capability ownership conserved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, choices=['rehearsal', 'production'])
    parser.add_argument('--backup', help='Fresh completed production common backup after write freeze')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    cluster_name = 'arcade-common-restore' if args.target == 'rehearsal' else 'arcade-postgresql'
    cluster = resource('games', 'cluster', cluster_name)
    pod = cluster['status']['currentPrimary']
    if cluster['status'].get('readyInstances') != 1:
        raise RuntimeError('Target cluster is not ready; resume only the named rehearsal copy if necessary')
    before = snapshot(pod)
    if not args.apply:
        print(f'Preflight only: {len(before[0])} identities → {len(before[1])} canonical accounts; no mutation.')
        return
    if args.target == 'production':
        frozen()
        if not args.backup:
            raise RuntimeError('A fresh production backup is required')
        backup = resource('games', 'backup', args.backup)
        started = dt.datetime.fromisoformat(backup['status']['startedAt'].replace('Z', '+00:00'))
        if backup['spec']['cluster']['name'] != cluster_name or backup['status'].get('phase') != 'completed' or (dt.datetime.now(dt.timezone.utc)-started).total_seconds() > 3600:
            raise RuntimeError('Backup must be completed, common and less than one hour old')
        for namespace, deployment_name in [('games', 'games'), ('slots', 'slots'), ('cka', 'cka')]:
            deployment = resource(namespace, 'deployment', deployment_name)
            frozen_at = max(dt.datetime.fromisoformat(c['lastUpdateTime'].replace('Z', '+00:00')) for c in deployment['status'].get('conditions', []) if c.get('lastUpdateTime'))
            if started < frozen_at:
                raise RuntimeError('Backup predates the web write freeze')
    # Execute with the non-superuser schema owner so definer RPCs do not acquire
    # postgres privileges. Expand psql includes before streaming into the pod.
    upgrade = (MIGRATIONS / 'unify-accounts.sql').read_text().replace('\\ir progress-functions.sql', (MIGRATIONS / 'progress-functions.sql').read_text())
    sql(pod, 'SET ROLE arcade;\n' + upgrade)
    sql(pod, 'SET ROLE arcade;\n' + (MIGRATIONS / 'account-contract.sql').read_text())
    verify(pod, before)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Canonical upgrade refused acceptance; private SQL/credentials withheld. Keep maintenance and inspect through an approved private operator session.')
