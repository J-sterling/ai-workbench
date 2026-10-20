"""Token usage of every Token Factory call this app makes, for the live Usage page.

Each call appends one line to USAGE_FILE (default var/usage.jsonl): time, model, kind,
tokens, seconds and an optional tag such as a run id. No prompt or log text is stored.
The web app and the scripts share the file, so the page shows both.
"""

import json
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from ai_workbench.config import settings

_lock = threading.Lock()


def _path() -> Path:
    return Path(settings.usage_file)


def record(kind: str, model: str, prompt_tokens: int, completion_tokens: int, seconds: float, tag: str = "") -> None:
    """Never raises: losing a usage line must not break a model call."""
    line = {"ts": round(time.time(), 3), "kind": kind, "model": model, "in": int(prompt_tokens or 0),
            "out": int(completion_tokens or 0), "s": round(seconds, 3), "tag": tag}
    try:
        path = _path()
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as f:
                f.write(json.dumps(line) + "\n")
    except OSError:
        pass


def _read() -> list[dict]:
    path = _path()
    if not path.exists():
        return []
    out = []
    with _lock, path.open() as f:
        for raw in f:
            try:
                out.append(json.loads(raw))
            except ValueError:
                continue
    return out


def cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    """USD estimate from PRICES ({model: [input, output] per 1M tokens}); None when no price is set."""
    price = settings.prices.get(model)
    if not price:
        return None
    return (tokens_in * price[0] + tokens_out * (price[1] if len(price) > 1 else 0)) / 1_000_000


def summary(now: float | None = None) -> dict:
    now = now or time.time()
    lines = _read()
    day_start = datetime.fromtimestamp(now, UTC).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def totals(rows: list[dict]) -> dict:
        costs = [cost(r["model"], r["in"], r["out"]) for r in rows]
        priced = [c for c in costs if c is not None]
        return {
            "calls": len(rows),
            "in": sum(r["in"] for r in rows),
            "out": sum(r["out"] for r in rows),
            "seconds": round(sum(r["s"] for r in rows), 1),
            "cost": round(sum(priced), 6) if priced else None,
            "unpriced_calls": len(costs) - len(priced),
        }

    today = [r for r in lines if r["ts"] >= day_start]
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in today:
        by_model[(r["model"], r["kind"])].append(r)

    # Tokens per minute over the last hour, oldest first, including empty minutes.
    minute_now = int(now // 60)
    per_minute = {m: {"in": 0, "out": 0, "calls": 0} for m in range(minute_now - 59, minute_now + 1)}
    for r in lines:
        m = int(r["ts"] // 60)
        if m in per_minute:
            per_minute[m]["in"] += r["in"]
            per_minute[m]["out"] += r["out"]
            per_minute[m]["calls"] += 1

    return {
        "now": now,
        "today": totals(today),
        "all_time": totals(lines),
        "by_model": sorted(
            ({"model": m, "kind": k, **totals(rows)} for (m, k), rows in by_model.items()),
            key=lambda x: x["in"] + x["out"], reverse=True,
        ),
        "per_minute": [{"minute": m * 60, **v} for m, v in sorted(per_minute.items())],
        "recent": [{**r, "cost": cost(r["model"], r["in"], r["out"])} for r in lines[-25:]][::-1],
        "priced_models": sorted(settings.prices),
    }
