"""Append-only audit log: one JSON line per question, definition change, export and notes run.

Records who did what, for which house, and the redacted question where there is one. Result values
and note text are never written here.

Tamper-evident: each line carries the hash of the line before it and its own hash, so editing,
deleting or reordering a line breaks the chain. `uv run axon audit-verify` checks it. (In production
the log would also be shipped to write-once storage, so the chain can't simply be rebuilt.)
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from axon.config import AUDIT_DIR

GENESIS = "0" * 64


def _default_path() -> Path:
    return Path(os.environ["AXON_AUDIT_PATH"]) if os.environ.get("AXON_AUDIT_PATH") else AUDIT_DIR / "audit.jsonl"


def _digest(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


class AuditLog:
    def __init__(self, path: Path | None = None):
        self.path = path or _default_path()

    def _last_hash(self) -> str:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return GENESIS
        with self.path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell() - 1
            while pos > 0:
                f.seek(pos - 1)
                if f.read(1) == b"\n":
                    break
                pos -= 1
            f.seek(max(pos, 0))
            last = json.loads(f.readline())
        return last.get("hash", GENESIS)

    def write(self, **fields) -> str:
        event_id = uuid.uuid4().hex[:12]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {"event_id": event_id, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **fields,
                  "prev": self._last_hash()}
        record["hash"] = _digest(record)
        with self.path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return event_id

    def verify(self) -> tuple[bool, str]:
        """Walk the chain. Lines from before chaining began (no hash) are reported, not judged."""
        if not self.path.exists():
            return True, "no audit log yet"
        prev, checked, legacy = None, 0, 0
        for n, line in enumerate(self.path.read_text().splitlines(), start=1):
            record = json.loads(line)
            if "hash" not in record:
                if prev is not None:
                    return False, f"line {n} has no hash after the chain began"
                legacy += 1
                continue
            if prev is not None and record.get("prev") != prev:
                return False, f"line {n} does not follow line {n - 1}: a line was edited, removed or reordered"
            if _digest(record) != record["hash"]:
                return False, f"line {n} was changed after it was written"
            prev, checked = record["hash"], checked + 1
        return True, f"{checked} lines verified" + (f"; {legacy} earlier lines from before chaining" if legacy else "")

    def tail(self, n: int = 20) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()[-n:]
        return [json.loads(line) for line in lines]
