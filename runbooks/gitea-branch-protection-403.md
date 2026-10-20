# Gitea branch protection returns 403 on re-run, or blocks the first commit

Tags: gitea, api, idempotency, branch-protection, gitops

## Symptoms
- Re-running a playbook that protects a branch fails with HTTP 403 `Branch protection already exist`.
- Or: seeding a new repo fails on every commit with 403 `user cannot commit to repo` after `main` was protected.

## Root cause
- Gitea returns 403 (not 409) when the protection already exists, so a task that only tolerates 409 is not idempotent.
- Gitea's push protection is name-based: protecting `main` before it exists blocks even the first commit that would create it.

## Fix
- Treat 403 with that exact message as "already done"; still fail on any other 403.
- Protect the branch after seeding the initial content, not before.

## Needs approval
None for the playbook change. Removing protection from a live branch needs approval.
