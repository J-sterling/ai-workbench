"""Check that each test log retrieves the right runbook. Needs no database.

Run: uv run scripts/eval_retrieval.py
"""

import math
import sys
from pathlib import Path

from ai_workbench.embeddings import embed, embed_query
from ai_workbench.kb import log_query

ROOT = Path(__file__).parent.parent

# (log text or samples/ file, expected runbook file)
CASES = [
    ("samples/01-garage-down.log", "s3-backend-garage-down.md"),
    ("samples/02-ci-checkout-dns.log", "act-runner-job-dns.md"),
    ("samples/03-blank-s3-creds.log", "terraform-s3-blank-credentials.md"),
    ("samples/04-php2shell-precheck.log", "php2shell-cve-2026-109618.md"),
    ('fatal: [web-02]: FAILED! => {"msg": "PHP 8.2.29 is vulnerable to CVE-2026-109619. Patch PHP to 8.2.35 or later before deploying."}',
     "php2shell-cve-2026-109618.md"),
    ("ERROR! Syntax Error while loading YAML.\n  found unknown escape character 's'\nThe offending line appears to be:\n    shell: \"ip addr | grep -oP '(?<=inet\\s)\\d+'\"",
     "yaml-regex-escapes.md"),
    ('fatal: [runner-01]: FAILED! => {"msg": "Error: Failed to get existing workspaces: RequestError: send request failed: dial tcp 10.0.0.5:3900: connect: connection refused"}',
     "s3-backend-garage-down.md"),
    ('TASK [Set DHCP range] ok: [router] => {"rc": 0}\nTASK [Verify] fatal: [router]: FAILED! => {"msg": "show service dhcp-server: range not configured after set"}',
     "vyos-dhcp-server-noninteractive-bug.md"),
    ('TASK [Wait for Gitea web UI] FAILED - RETRYING: (1 retries left).\nfatal: [git-ct]: FAILED! => {"msg": "Status code was -1: Connection refused", "url": "http://localhost:3000/"}',
     "gitea-first-boot-healthcheck-timeout.md"),
    ('fatal: [git-ct]: FAILED! => {"status": 403, "json": {"message": "Branch protection already exist"}}',
     "gitea-branch-protection-403.md"),
    ('The CustomResourceDefinition "applicationsets.argoproj.io" is invalid: metadata.annotations: Too long: must have at most 262144 bytes',
     "argocd-annotation-too-long.md"),
    ("ComparisonError: Failed to load target state: rpc error: ssh: handshake failed: knownhosts: key is unknown",
     "argocd-ssh-known-hosts.md"),
    ('fatal: [cp-01]: FAILED! => {"stderr": "error: error when creating \\"install.yaml\\": Post \\"https://127.0.0.1:6443/api\\": read tcp: connection reset by peer"}',
     "kubectl-tunnel-connection-reset.md"),
    ("Run actions/checkout@v4\nfatal: unable to access 'http://gitea:3000/ops/infra.git/': Could not resolve host: gitea",
     "act-runner-job-dns.md"),
    ('fatal: [cp-01]: FAILED! => {"cmd": "talosctl patch mc --patch @single-node-patch.yaml", "stderr": "error patching: lookup failed"}',
     "talos-delete-patch-lookup-failed.md"),
]


def cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / (math.hypot(*a) * math.hypot(*b))


def main() -> int:
    books = sorted((ROOT / "runbooks").glob("*.md"))
    vecs = embed([b.read_text() for b in books])
    hits = 0
    for log, expected in CASES:
        path = ROOT / log
        text = path.read_text() if path.exists() else log
        q = embed_query(log_query(text))
        ranked = sorted(((cos(q, v), b.name) for b, v in zip(books, vecs)), reverse=True)
        top_score, top = ranked[0]
        ok = top == expected
        hits += ok
        rank = [n for _, n in ranked].index(expected) + 1
        print(f"{'PASS' if ok else 'FAIL'}  top={top} ({top_score:.3f})  expected rank={rank}  margin={top_score - ranked[1][0]:.3f}")
    print(f"\nTop-1 accuracy: {hits}/{len(CASES)}")
    return 0 if hits == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
