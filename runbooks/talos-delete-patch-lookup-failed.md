# Re-applying a Talos $patch: delete fails with "lookup failed"

Tags: talos, kubernetes, idempotency, talosctl

## Symptoms
- First run of `talosctl patch` succeeds; re-running the playbook fails with `lookup failed`.
- The patch file uses `$patch: delete` (e.g. removing the control-plane NoSchedule taint on a single-node cluster).

## Root cause
A `$patch: delete` patch errors when the thing it deletes is already gone, unlike normal set-style patches, which no-op.

## Fix
Tolerate exactly that error text on re-run (`failed_when: r.rc != 0 and 'lookup failed' not in r.stderr`); any other error must still fail the task.

## Needs approval
None.
