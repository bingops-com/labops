"""Dispatch read-only CI for Renovate PRs created with the repository's ephemeral token."""
import json
import os
import re
import urllib.parse
import urllib.request

WORKFLOWS = ['dev-vm-test.yml', 'repository-validation.yml', 'ansible-lint.yml', 'terraform-lint.yml', 'yamllint.yml']


def main():
    repository = os.environ['GITHUB_REPOSITORY']
    if repository != 'bingops-com/labops':
        raise RuntimeError('This runner owns only the LabOps development tooling')
    base = f'https://api.github.com/repos/{repository}'

    def api(path, data=None):
        request = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, headers={
            'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
            'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json',
            'X-GitHub-Api-Version': '2022-11-28',
        })
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
        return json.loads(raw) if raw else None

    count = 0
    for pr in api('/pulls?state=open&per_page=100'):
        head = pr['head']
        if pr['user']['login'] != 'github-actions[bot]' or head['repo']['full_name'] != repository or not head['ref'].startswith('renovate/'):
            continue
        if not re.fullmatch('[a-f0-9]{40}', head['sha']):
            raise RuntimeError('Invalid branch identity')
        query = urllib.parse.urlencode({'head_sha': head['sha'], 'per_page': 100})
        runs = api('/actions/runs?' + query)['workflow_runs']
        dispatched = {run['path'].rsplit('/', 1)[-1] for run in runs if run['event'] == 'workflow_dispatch'}
        for workflow in WORKFLOWS:
            if workflow in dispatched:
                continue
            api('/actions/workflows/' + workflow + '/dispatches', {'ref': head['ref']})
            count += 1
        print(f'PR #{pr["number"]}: validation requested for {head["sha"][:12]}')
    print(f'Dispatched {count} validation workflows; no PR was merged.')


if __name__ == '__main__':
    main()
