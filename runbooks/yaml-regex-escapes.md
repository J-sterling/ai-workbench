# Regex with \s or \d breaks the YAML parser in a playbook

Tags: ansible, yaml, regex, grep, parsing

## Symptoms
- Playbook fails to load, or a stricter YAML parser rejects it, on a line like
  `shell: "ip addr | grep -oP '(?<=inet\s)\d+(\.\d+){3}'"`.
- Errors such as `found unknown escape character` or `while scanning a double-quoted scalar`.

## Root cause
Inside a YAML double-quoted string, backslash starts an escape sequence. `\s` and `\d` are not valid YAML escapes. Some parsers tolerate them, stricter ones fail.

## Fix
Use `\\s` / `\\d` inside double quotes, or use a single-quoted or block scalar (`|`) so backslashes are literal:
```yaml
shell: |
  ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'
```
Run `ansible-playbook --syntax-check` and `ansible-lint` in CI to catch it before a live run.

## Needs approval
None.
