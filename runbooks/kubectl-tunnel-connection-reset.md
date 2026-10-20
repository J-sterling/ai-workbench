# Large kubectl apply over an SSH tunnel fails part-way: connection reset by peer

Tags: kubernetes, kubectl, ssh-tunnel, retries, partial-apply

## Symptoms
- `kubectl apply` of a big manifest (~50 resources) fails mid-way with `connection reset by peer` or `unexpected EOF`.
- Most resources exist afterwards, but some CRDs or ServiceAccounts are missing.

## Root cause
A transient reset on the SSH tunnel to the cluster API. Long single applies are more likely to hit it. The cluster is fine.

## Fix
`kubectl apply` is idempotent, so retry until it returns rc 0:
```yaml
- command: kubectl apply --server-side -f install.yaml
  register: r
  retries: 5
  delay: 10
  until: r.rc == 0
```

## Needs approval
None.
