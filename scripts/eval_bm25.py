"""Compare BM25, vector search and a hybrid (RRF) on the retrieval test cases. Needs no database.

Run: uv run scripts/eval_bm25.py
"""

import math
import re
import sys
from collections import Counter

from eval_retrieval import CASES, ROOT, cos

from ai_workbench.embeddings import embed, embed_query
from ai_workbench.kb import log_query

# Reworded symptoms with none of the literal error strings: where BM25 should be weakest.
PARAPHRASES = [
    ("terraform can't reach the state bucket, nothing is listening on the s3 port", "s3-backend-garage-down.md"),
    ("the CI pipeline cannot find the git server by its name during checkout", "act-runner-job-dns.md"),
    ("terraform backend login rejected because the access key is empty", "terraform-s3-blank-credentials.md"),
    ("my playbook won't load, the regular expression inside a quoted string breaks parsing", "yaml-regex-escapes.md"),
    ("argo cd can't install its CRDs because the stored metadata is too big", "argocd-annotation-too-long.md"),
]

TOKEN = re.compile(r"[a-z0-9_]+(?:[.\-][a-z0-9_]+)*")
K1, B = 1.5, 0.75
RRF_K = 60


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


class BM25:
    def __init__(self, docs: list[str]):
        self.docs = [Counter(tokens(d)) for d in docs]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lens) / len(self.lens)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q = set(tokens(query))
        out = []
        for d, length in zip(self.docs, self.lens):
            s = 0.0
            for t in q & d.keys():
                tf = d[t]
                s += self.idf[t] * tf * (K1 + 1) / (tf + K1 * (1 - B + B * length / self.avg))
            out.append(s)
        return out


def ranking(scores: list[float], names: list[str]) -> list[tuple[float, str]]:
    return sorted(zip(scores, names), reverse=True)


def rrf(*rankings: list[tuple[float, str]]) -> list[tuple[float, str]]:
    fused = Counter()
    for r in rankings:
        for i, (_, name) in enumerate(r):
            fused[name] += 1 / (RRF_K + i + 1)
    return sorted(((s, n) for n, s in fused.items()), reverse=True)


def verdict(ranked: list[tuple[float, str]], expected: str) -> tuple[bool, int, float]:
    """(top-1 correct, rank of expected, relative margin of top over second)."""
    names = [n for _, n in ranked]
    top, second = ranked[0][0], ranked[1][0]
    margin = (top - second) / top if top else 0.0
    return names[0] == expected, names.index(expected) + 1, margin


def label(case: str) -> str:
    text = case.removeprefix("samples/").replace("\n", " ")
    return (text[:38] + "…") if len(text) > 39 else text


def run(title: str, cases: list[tuple[str, str]], names, bm25, vecs) -> dict:
    print(f"\n{title}")
    print(f"{'case':<40} {'BM25':>14} {'vector':>14} {'hybrid':>14}")
    hits = Counter()
    for case, expected in cases:
        path = ROOT / case
        query = log_query(path.read_text()) if path.exists() else log_query(case)
        q = embed_query(query)
        rb = ranking(bm25.scores(query), names)
        rv = ranking([cos(q, v) for v in vecs], names)
        rh = rrf(rb, rv)
        cells = []
        for method, r in (("bm25", rb), ("vector", rv), ("hybrid", rh)):
            ok, rank, margin = verdict(r, expected)
            hits[method] += ok
            cells.append(f"{'ok' if ok else f'MISS r{rank}'} {margin:>5.0%}")
        print(f"{label(case):<40} " + " ".join(f"{c:>14}" for c in cells))
    n = len(cases)
    print(f"{'top-1':<40} " + " ".join(f"{f'{hits[m]}/{n}':>14}" for m in ("bm25", "vector", "hybrid")))
    return hits


def main() -> int:
    books = sorted((ROOT / "runbooks").glob("*.md"))
    names = [b.name for b in books]
    texts = [b.read_text() for b in books]
    bm25 = BM25(texts)
    vecs = embed(texts)
    print("Margin = how far the top score is ahead of the second, as a share of the top score.")
    run("Labelled cases (literal error text)", CASES, names, bm25, vecs)
    run("Paraphrased symptoms (no literal error text)", PARAPHRASES, names, bm25, vecs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
