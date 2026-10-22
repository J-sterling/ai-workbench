"""Simulated host the agent runs commands against, so demos are safe and repeatable.

Each sample log can have a fixture, samples/<name>.sandbox.json:

    {"commands": [{"match": "<regex>", "output": "...", "when": "flag" | "!flag"}],
     "actions":  [{"match": "<regex>", "output": "...", "when": ..., "sets": ["flag"]}]}

`commands` answer read-only diagnostics; `actions` are what an approved fix does.
An action can set flags, and later commands can depend on them, so a diagnostic run
after the fix sees the fixed state. First matching entry wins.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SAMPLES = Path(__file__).parent.parent.parent / "samples"

# Diagnostics must start with one of these. Anything else has to go through
# propose_fix and a human approval, even in the sandbox.
READ_ONLY = re.compile(
    r"^(docker (ps|logs|inspect|images|volume (ls|inspect)|network (ls|inspect)|compose (ps|logs))"
    r"|ls|cat|head|tail|grep|stat|file|find|wc|echo|whoami|id|hostname|uptime|date|df|du|free"
    r"|getent|dig|nslookup|host|ping|curl|nc|ss|netstat|ip (a|addr|r|route)"
    r"|terraform (version|show|validate|providers|state list|workspace (list|show))"
    r"|git (status|log|diff|show|remote)|kubectl (get|describe|logs)|journalctl|systemctl (status|is-active)"
    r"|php|dpkg (-l|-s|--list|--status)|dpkg-query (-l|-W|-s)|apt (list|policy|show)|apt-cache (policy|show))"
    # The tool name must be followed by a space or the end: "file=x rm -rf /" is not "file".
    r"(?=\s|$)"
)
# Redirects that only throw output away are harmless, so they are removed before checking.
DISCARD = re.compile(r"\s[12]?>\s*/dev/null|\s2>&1|\s(-o|--output)\s+/dev/null(?=\s|$)")
# Every command between these runs on its own, so each must pass the check.
SEPARATORS = re.compile(r"&&|\|\||;|\||&|\n")

# (pattern, why it is refused). Checked on the whole command, then on each part.
REFUSED = [
    (re.compile(r">|<\(|\$\(|`"), "redirects and command substitution can write files or hide a command"),
    (re.compile(r"\bxargs\b"), "xargs runs a command for each input; to search file contents use grep -rl PATTERN DIR"),
    (re.compile(r"\btee\b|\bsed\s+-i"), "this writes files"),
    # Values of secrets must never reach the model; their length is enough to see if they are set.
    (re.compile(r"\$\{?[A-Z0-9_]*(KEY|SECRET|TOKEN|PASS|CREDENTIAL)[A-Z0-9_]*\b(?!\})|"
                r"\$\{[A-Z0-9_]*(KEY|SECRET|TOKEN|PASS|CREDENTIAL)[A-Z0-9_]*\}|\$\{!", re.I),
     "this prints a secret; print its length instead, e.g. echo ${#AWS_ACCESS_KEY_ID}"),
    (re.compile(r"(^|[\s/=])(\.env\b|\.ssh/|id_rsa|id_ed25519|\.aws/|\.netrc|\.pgpass|/etc/shadow|vault\.ya?ml|"
                r"credentials\b|secrets?\.\w+|[\w.-]+\.(pem|key)\b)", re.I),
     "this reads a file that holds secrets"),
    (re.compile(r"/proc/\S*environ|169\.254\.169\.254|metadata\.google\.internal|getent\s+g?shadow", re.I),
     "this reads process environments, cloud metadata or password hashes, which hold secrets"),
]
PER_TOOL = [
    (re.compile(r"^find\b"), re.compile(r"\s-(delete|exec|execdir|ok|okdir|fprint0?|fprintf|fls)\b"),
     "find can delete files or run commands with these options"),
    (re.compile(r"^curl\b"),
     re.compile(r"\s(-[a-zA-Z]*[oOTXdFKcD]|--(output|remote-name|upload-file|request|data[\w-]*|form|json|config|"
                r"cookie-jar|dump-header|trace[\w-]*|stderr))\b"),
     "curl may only read; these options send data or write files"),
    (re.compile(r"^git\b"), re.compile(r"--output|^git remote\s+(?!(-v|show\s+\S+)\s*$)"),
     "this changes the repository or writes a file"),
    (re.compile(r"^ip\b"), re.compile(r"\b(add|del|delete|change|replace|flush|set|append)\b"), "this changes network settings"),
    (re.compile(r"^nc\b"), re.compile(r"^(?!.*\s-[a-zA-Z]*z)|\s-[a-zA-Z]*[elc]\b"),
     "nc may only check whether a port is open: nc -zv HOST PORT"),
    (re.compile(r"^ss\b"), re.compile(r"\s-[a-zA-Z]*K|--kill"), "this kills sockets"),
    (re.compile(r"^date\b"), re.compile(r"\s(-s|--set)\b"), "this sets the clock"),
    (re.compile(r"^hostname\b"), re.compile(r"^hostname\s+(?!-[fiIsAd]\b)\S"), "this sets the hostname"),
    (re.compile(r"^kubectl\b"), re.compile(r"\bsecrets?\b", re.I), "this prints Kubernetes secrets"),
    (re.compile(r"^docker inspect\b"), re.compile(r"^(?!.*\s(-f|--format)[\s=])|\b(Env|Config)\b"),
     "full docker inspect output includes environment secrets; use --format with the fields you need, "
     "e.g. --format '{{json .Mounts}}'"),
    (re.compile(r"^php\b"), re.compile(r"^(?!php\s+(-v|--version)\s*$)"),
     "php may only report its version (php -v); other options run code or print settings that can hold secrets"),
    (re.compile(r"^terraform providers\b"), re.compile(r"\s(lock|mirror)\b"), "this writes provider files"),
    (re.compile(r"^(cat|head|tail)\b"), re.compile(r"[?*\[]"),
     "use the exact file path; wildcards can reach files that hold secrets"),
    (re.compile(r"^journalctl\b"), re.compile(r"--(vacuum[\w-]*|rotate|flush|relinquish-var|setup-keys)\b"),
     "this deletes or rotates logs"),
    # These never finish, so a real executor would hang.
    (re.compile(r"^(tail|journalctl|docker logs|kubectl logs)\b"), re.compile(r"\s(-[a-zA-Z]*[fF]|--follow)\b"),
     "following output never finishes; read the last lines instead, e.g. --tail 50"),
    (re.compile(r"^ping\b"), re.compile(r"^(?!.*\s-c\s*\d)"), "ping must stop on its own: ping -c 3 HOST"),
]


# Fixes matching this are flagged so the approver looks twice.
DESTRUCTIVE = re.compile(
    r"\b(rm -[a-z]*[rf]|docker (rm|volume (rm|prune)|system prune)|terraform destroy|drop (table|database)|mkfs)\b|--force\b",
    re.I,
)


def segments(command: str) -> list[str]:
    return [s.strip() for s in re.split(r"&&|\|\||;|\|", command) if s.strip()]


def refusal(command: str) -> str | None:
    """Why a diagnostic is refused, or None if it is read-only."""
    command = DISCARD.sub(" ", command).strip()
    if not command:
        return "empty command"
    # Quotes and backslashes are dropped first, so cat '.env' is still seen as .env.
    plain = re.sub(r"[\"'\\]", "", command)
    for pattern, why in REFUSED:
        if pattern.search(plain):
            return why
    for part in (p.strip() for p in SEPARATORS.split(command)):
        if not part:
            continue
        if not READ_ONLY.match(part):
            return f"'{part.split()[0]}' is not on the read-only list"
        for tool, bad, why in PER_TOOL:
            if tool.match(part) and bad.search(part):
                return why
    return None


def is_read_only(command: str) -> bool:
    return refusal(command) is None


def is_destructive(commands: list[str]) -> bool:
    return any(DESTRUCTIVE.search(c) for c in commands)


@dataclass
class Sandbox:
    commands: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)

    @classmethod
    def for_sample(cls, name: str) -> "Sandbox":
        path = SAMPLES / f"{name}.sandbox.json"
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(data.get("commands", []), data.get("actions", []))

    def _holds(self, entry: dict) -> bool:
        when = entry.get("when")
        if not when:
            return True
        return when[1:] not in self.flags if when.startswith("!") else when in self.flags

    def _find(self, entries: list[dict], command: str) -> dict | None:
        return next((e for e in entries if self._holds(e) and re.search(e["match"], command)), None)

    def run(self, command: str) -> str:
        """A read-only diagnostic. Callers check is_read_only() first."""
        hit = self._find(self.commands, command)
        return hit["output"] if hit else f"(sandbox) no simulated output for: {command}"

    def apply(self, command: str) -> str:
        """An approved fix. Each `&&`/`;` step runs in order and may change state."""
        out = []
        for step in segments(command):
            hit = self._find(self.actions, step)
            if hit:
                self.flags.update(hit.get("sets", []))
                out.append(hit["output"])
            elif is_read_only(step):  # a check inside the fix, e.g. "systemctl status" after an upgrade
                out.append(self.run(step))
            else:
                out.append(f"(sandbox) ran with no simulated effect: {step}")
        return "\n".join(o for o in out if o)
