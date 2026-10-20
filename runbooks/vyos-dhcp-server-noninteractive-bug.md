# VyOS dhcp-server settings don't apply when set non-interactively

Tags: vyos, dhcp, router, platform-bug

## Symptoms
- `set service dhcp-server ...` via `script-template` / `vbash` returns 0, but `show service dhcp-server` immediately afterwards shows no change.
- Other subtrees (interfaces, NAT, WireGuard, policy routing) apply fine the same way.
- New guests on that subnet never get a DHCP lease.

## Root cause
A platform bug in some VyOS rolling builds: the `service dhcp-server` subtree ignores non-interactive `set`, even when editing an existing leaf. It is not a syntax problem.

## Fix
Don't keep retrying syntax variations. Work around it: give workloads on that subnet static IPs (e.g. via Terraform cloud-init `ip_address` + `gateway`), or apply the DHCP change interactively. Check newer VyOS builds for a fix.

## Needs approval
Interactive changes on the router.
