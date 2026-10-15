"""Staff decisions on note findings: confirm or reject, per house, append-only (D-25)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from axon.config import DATA_DIR

REVIEWS_DIR = DATA_DIR / "reviews"


def key(resident_id: str, field: str, value: str) -> str:
    return f"{resident_id}|{field}|{value}"


class ReviewStore:
    def __init__(self, root: Path = REVIEWS_DIR):
        self.root = root

    def _path(self, tenant_id: str) -> Path:
        return self.root / f"{tenant_id}.json"

    def history(self, tenant_id: str) -> list[dict]:
        p = self._path(tenant_id)
        return json.loads(p.read_text())["events"] if p.exists() else []

    def decisions(self, tenant_id: str) -> dict[str, str]:
        """Latest decision per finding: 'confirm' or 'reject'."""
        out: dict[str, str] = {}
        for e in self.history(tenant_id):
            out[e["key"]] = e["decision"]
        return out

    def decide(self, tenant_id: str, resident_id: str, field: str, value: str, decision: str, user: str) -> None:
        if decision not in {"confirm", "reject"}:
            raise ValueError("decision must be confirm or reject")
        events = self.history(tenant_id)
        events.append({"key": key(resident_id, field, value), "decision": decision, "by": user,
                       "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(tenant_id).write_text(json.dumps({"events": events}, indent=2) + "\n")
