# Local verification — 2026-10-13

Reviewed application sources pinned by the rehearsal workflow:

- Games: `4670a11f8d5deba82c870e48d82a4ab453fb1f33`.
- Slots: `d2ffcdff42ec7541166ea23fdb4374e0a480a9bf`.

Passed locally:

- Games: 106 Go tests with the race detector, including refusal to bootstrap
  an unprepared shared database; `go vet`; chart security/preservation checks.
- Slots: 18 Go tests with the race detector, including stale-password session
  rejection and unprepared shared database refusal; `go vet`; WASM/Next build,
  TypeScript, workflow lint and chart source-database preservation checks.
- Slots browser suite: four scenarios, 148 accessibility states, zero failures;
  all 14 games, restored artwork, mobile/desktop dialogs, multiplayer seat/hand
  selection and offline WASM practice. Continuous sea ambience stays removed.
- Shared accounts: real Games/Slots HTTP servers and synthetic PostgreSQL 17
  fixtures. Verified streamed import of restored source schemas, refusal to
  overwrite a staged target, two-password proofs, expired/invalid proof denial,
  atomic rollback, idempotence, account/ID/stat/balance conservation, both login
  directions, concurrent registration, common password/recovery and cross-site
  session revocation, used recovery-code refusal, independent dump/restore and
  reconnecting both servers after restore.
- Four helper tests: origin/redirect restrictions, private proof files,
  symlink overwrite refusal, mocked CNPG credential generation/escaping and
  dedicated rehearsal-secret selection. No real Kubernetes Secret was read.
- Staging, recovery and rehearsal Kustomize overlays render; rehearsal contains
  exactly three distinct non-archiving clusters. New YAML/Python parse, Bash
  syntax and actionlint pass. Existing Games release gate: nine unit tests and
  offline pin agreement pass; production pins are unchanged.

Not performed:

- GitHub CI (application commits have not been pushed). The added workflow
  uses PostgreSQL 18.4 and compatible containerized clients.
- Migration/restore of actual production data, proof collection from players,
  Barman restore/WAL acceptance or live NetworkPolicy enforcement. Only the two
  source cluster image specifications were read; both report PostgreSQL 18.4.
- `yamllint`: the local launcher lacks its Python module. YAML was parsed and
  Kustomize-rendered instead. ShellCheck is unavailable; Bash syntax was checked.

No production resource, credential, account, database or volume was changed.
No push, PR or deployment was performed. Games remains running separately on
`0.0.0.0:3778` with its existing local development database; the migration tests
use isolated, disposable fixtures and leave that service intact.

Reconstruction, non-Git input recovery, retry semantics, lifecycle order and
safe verification are owned by [the runbook](README.md). These results do not
authorize or establish production cutover acceptance.
