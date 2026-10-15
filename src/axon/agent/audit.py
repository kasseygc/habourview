"""Append-only audit log: one JSON line per question (D-18).

Records who asked, for which house, the redacted question, what ran and how long it took.
Result values are never written here.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from axon.config import AUDIT_DIR


class AuditLog:
    def __init__(self, path: Path = AUDIT_DIR / "audit.jsonl"):
        self.path = path

    def write(self, **fields) -> str:
        event_id = uuid.uuid4().hex[:12]
        record = {"event_id": event_id, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **fields}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return event_id

    def tail(self, n: int = 20) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()[-n:]
        return [json.loads(line) for line in lines]
