# ArgoCD install fails: metadata.annotations: Too long

Tags: argocd, kubernetes, kubectl, crd, server-side-apply

## Symptoms
- `kubectl apply -f install.yaml` fails on the `applicationsets.argoproj.io` CRD.
- `The CustomResourceDefinition "applicationsets.argoproj.io" is invalid: metadata.annotations: Too long: must have at most 262144 bytes`.

## Root cause
Client-side `kubectl apply` stores the whole object in the `last-applied-configuration` annotation. The ApplicationSet CRD schema is larger than Kubernetes' 256KB annotation limit. Known upstream issue (argoproj/argo-cd#11269).

## Fix
```bash
kubectl apply --server-side --force-conflicts -n argocd -f install.yaml
```
`--force-conflicts` is needed if some resources were already applied client-side.

## Needs approval
`--force-conflicts` takes field ownership from other managers; confirm nothing else manages these resources.
