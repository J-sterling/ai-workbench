# Gitea health check times out on first boot

Tags: gitea, docker, healthcheck, retries, sqlite

## Symptoms
- `uri` / `wait_for` task polling Gitea's web UI fails after its retries are exhausted.
- `docker logs gitea` shows it is still initialising (database migration, issue indexer).
- Re-running the playbook a few minutes later succeeds.

## Root cause
Gitea's first-boot SQLite and issue-indexer initialisation can take several minutes on slow hardware. A retry budget that is fine for a simple container is too short.

## Fix
Size the retry budget generously for first boot, e.g. `retries: 40`, `delay: 10`. Optionally check `docker logs` progress instead of a fixed timeout.

## Needs approval
None.
