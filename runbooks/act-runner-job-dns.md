# Gitea Actions job can't resolve the Gitea host: Could not resolve host

Tags: gitea, act_runner, ci, docker-network, dns

## Symptoms
- First CI run fails at `actions/checkout@v4` with `Could not resolve host: gitea`.
- `act_runner`'s own container logs show nothing useful; step output is only in the job log.

## Root cause
act_runner's Docker executor puts every job container on its own isolated network, which cannot see the `gitea` container on the compose stack's network.

## Fix
Create a shared network (e.g. `gitea-net`) for both `gitea` and `act_runner`, and set it for job containers in the runner config:
```yaml
container:
  network: gitea-net
```
Mount the config via `CONFIG_FILE` and ship it from the playbook so a rebuild keeps the fix.

## Needs approval
Restarting the runner (in-flight jobs are lost).
