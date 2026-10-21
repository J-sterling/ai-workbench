"""Turn Nebius FOCUS 1.2 billing CSVs into the dashboard's Bills data.

Reads var/finops/raw/*.csv (from scripts/finops-export.sh) and docs/tracker/finops_manual.json.
Writes var/finops/bills.json (daily cost rows) and var/finops/plan.json (one row of budget and rates).
Account, contract and resource IDs are dropped; the endpoint is named, not identified.

Usage: uv run scripts/finops_build.py
"""

import csv
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "var/finops/raw"
OUT = ROOT / "var/finops"
MANUAL = ROOT / "docs/tracker/finops_manual.json"


def item_of(row: dict) -> str:
    """A readable line item: what was charged, without IDs."""
    if row["ChargeCategory"] == "Tax":
        return "Tax"
    kind = {"computeinstance": "Demo endpoint", "computedisk": "Endpoint disk"}.get(row["ResourceType"], row["ResourceType"])
    desc = row["ChargeDescription"].split(". ")[-1]  # "Non-GPU AMD Epyc Genoa. CPU" -> "CPU"
    return kind if kind == "Endpoint disk" else f"{kind} {desc}"


def build() -> tuple[list[dict], dict]:
    manual = json.loads(MANUAL.read_text())
    totals: dict[tuple, float] = defaultdict(float)
    qty: dict[tuple, float] = defaultdict(float)
    units: dict[tuple, str] = {}
    for path in sorted(RAW.glob("*.csv")):
        for r in csv.DictReader(path.open()):
            key = (r["ChargePeriodStart"][:10], "Nebius AI Cloud", r["ServiceName"], item_of(r))
            totals[key] += float(r["BilledCost"] or 0)
            if r["ConsumedQuantity"] not in ("", "NULL"):
                qty[key] += float(r["ConsumedQuantity"])
                units[key] = r["ConsumedUnit"]
    rows = [
        {"id": f"{d}-{i}", "date": d, "provider": p, "service": s, "item": i, "quantity": round(qty.get(k, 0), 3),
         "unit": units.get(k, ""), "cost_usd": round(c, 6), "source": "Nebius billing export"}
        for k, c in sorted(totals.items()) for d, p, s, i in [k]
    ]
    for m in manual["manual_costs"]:
        rows.append({"id": f'{m["date"]}-{m["item"]}', "date": m["date"], "provider": m["provider"], "service": m["service"], "item": m["item"],
                     "quantity": m.get("quantity", 0), "unit": m.get("unit", ""),
                     "cost_usd": float(m["cost_usd"]), "source": m.get("source", "Console reading")})
    plan = {
        "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "budget_usd_month": manual["budget_usd_month"],
        "balance_usd": manual["balance"]["usd"],
        "balance_as_of": manual["balance"]["as_of"],
        "run_start": manual["run_window"]["start"],
        "run_end": manual["run_window"]["end"],
        "endpoint_usd_per_hour": manual["rates"]["endpoint_usd_per_hour"],
        "disk_usd_per_hour": manual["rates"]["disk_usd_per_hour"],
        "pending": "; ".join(p["provider"] for p in manual["pending_readings"]),
    }
    return rows, plan


if __name__ == "__main__":
    rows, plan = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bills.json").write_text(json.dumps(rows, indent=1))
    (OUT / "plan.json").write_text(json.dumps([plan], indent=1))
    print(f"{len(rows)} cost rows, ${sum(r['cost_usd'] for r in rows):.4f} total -> var/finops/bills.json, plan.json")
