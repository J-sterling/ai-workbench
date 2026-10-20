# ArgoCD can't reach a self-hosted Git server: knownhosts: key is unknown

Tags: argocd, ssh, gitea, gitops, known-hosts

## Symptoms
- Application sync status stuck at `Unknown`.
- `status.conditions` shows `ssh: handshake failed: knownhosts: key is unknown`.

## Root cause
ArgoCD's repo-server strictly verifies SSH host keys against the `argocd-ssh-known-hosts-cm` ConfigMap, which only ships with GitHub/GitLab/Bitbucket keys. A self-hosted Git server's key is not there. Re-applying the stock ArgoCD manifest resets the ConfigMap, so a one-off manual fix disappears.

## Fix
```bash
ssh-keyscan <git-host> > gitea.known_hosts
# merge into argocd-ssh-known-hosts-cm (keep the stock entries), then:
kubectl -n argocd rollout restart deploy argocd-repo-server
```
Make the playbook re-merge the key on every run, after the manifest apply.

## Needs approval
Restarting `argocd-repo-server` (brief sync interruption). Verify the scanned key out-of-band before trusting it.
