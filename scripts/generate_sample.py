"""Generate examples/sample.json with synthetic support tickets (fixed seed)."""

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

SEED = 42
N_TICKETS = 600
START = datetime(2026, 1, 1, tzinfo=UTC)
DAYS = 31

STATUSES = {"open": 0.12, "in_progress": 0.13, "resolved": 0.45, "closed": 0.30}
PRIORITIES = {"low": 0.30, "medium": 0.40, "high": 0.22, "critical": 0.08}
# Median resolution time in hours per priority.
MEDIAN_HOURS = {"low": 30, "medium": 18, "high": 8, "critical": 3}
CATEGORIES = {
    "billing": 0.22,
    "login": 0.18,
    "performance": 0.14,
    "integrations": 0.12,
    "mobile": 0.10,
    "notifications": 0.08,
    "reports": 0.07,
    "security": 0.05,
    "other": 0.04,
}

OUT = Path(__file__).resolve().parent.parent / "examples" / "sample.json"


def pick(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def make_ticket(rng: random.Random, i: int) -> dict:
    status = pick(rng, STATUSES)
    priority = pick(rng, PRIORITIES)
    created = START + timedelta(minutes=rng.randrange(DAYS * 24 * 60))
    resolved = None
    if status in ("resolved", "closed"):
        hours = rng.lognormvariate(0, 0.8) * MEDIAN_HOURS[priority]
        resolved = iso(created + timedelta(hours=hours))
    return {
        "id": f"TCK-{i:04d}",
        "status": status,
        "priority": priority,
        "category": pick(rng, CATEGORIES),
        "created_at": iso(created),
        "resolved_at": resolved,
    }


def main() -> None:
    rng = random.Random(SEED)
    tickets = [make_ticket(rng, i) for i in range(1, N_TICKETS + 1)]
    tickets.sort(key=lambda t: t["created_at"])
    payload = {
        "title": "Reporte de soporte",
        "period": {"start": "2026-01-01", "end": "2026-01-31"},
        "tickets": tickets,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(tickets)} tickets to {OUT}")


if __name__ == "__main__":
    main()
