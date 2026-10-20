# VyOS changes made via vyatta-cfg-cmd-wrapper silently do nothing

Tags: vyos, router, automation, commit-confirm

## Symptoms
- An Ansible task running `vyatta-cfg-cmd-wrapper set ...` returns rc 0, but `show` afterwards proves nothing changed.
- `commit-confirm` appears to run but the router never auto-reverts.

## Root cause
`vyatta-cfg-cmd-wrapper` is unreliable for non-interactive use: it silently no-ops on invalid config paths and does not implement `commit-confirm` at all.

## Fix
Run config through real VyOS CLI functions instead:
```bash
/bin/vbash -c 'source /opt/vyatta/etc/functions/script-template
configure
set interfaces ethernet eth1 description lab
commit-confirm 2
confirm
save'
```
Always verify with a `show` after the change, and use `commit-confirm` so a bad change auto-reverts.

## Needs approval
Any router config change. A bad commit can cut off the only management path.
