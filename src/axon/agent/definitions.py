"""House definitions: the answers to clarifying questions, saved per house and versioned (D-13).

Stored as one JSON file per house. Every change appends a version (who, when, what);
nothing is overwritten, so a chart can always say which definition it used.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from axon.agent.glossary import GLOSSARY, Choice
from axon.agent.registry import METRICS
from axon.config import DEFINITIONS_DIR

GENERIC_PREFIX = "metric:"


@dataclass(frozen=True)
class Definition:
    term: str
    choice_id: str
    label: str
    version: int
    defined_by: str
    defined_at: str


def choice_for(term: str, choice_id: str) -> Choice:
    if choice_id.startswith(GENERIC_PREFIX):
        metric = METRICS[choice_id.removeprefix(GENERIC_PREFIX)]
        return Choice(choice_id, metric.label, {"metric": metric.id})
    for c in GLOSSARY[term].choices:
        if c.id == choice_id:
            return c
    raise KeyError(f"{choice_id!r} is not a choice for {term!r}")


class DefinitionStore:
    def __init__(self, root: Path = DEFINITIONS_DIR):
        self.root = root

    def _path(self, tenant_id: str) -> Path:
        return self.root / f"{tenant_id}.json"

    def _read(self, tenant_id: str) -> dict:
        p = self._path(tenant_id)
        return json.loads(p.read_text()) if p.exists() else {"terms": {}}

    def current(self, tenant_id: str) -> dict[str, Definition]:
        out = {}
        for term, versions in self._read(tenant_id)["terms"].items():
            latest = versions[-1]
            if latest["choice_id"] is not None:
                out[term] = Definition(term, latest["choice_id"], latest["label"], latest["version"],
                                       latest["defined_by"], latest["defined_at"])
        return out

    def history(self, tenant_id: str, term: str) -> list[dict]:
        return self._read(tenant_id)["terms"].get(term, [])

    def save(self, tenant_id: str, term: str, choice_id: str | None, user: str) -> None:
        """choice_id=None clears the definition (the next question will ask again)."""
        label = choice_for(term, choice_id).label if choice_id else None
        data = self._read(tenant_id)
        versions = data["terms"].setdefault(term, [])
        versions.append(
            {
                "version": len(versions) + 1,
                "choice_id": choice_id,
                "label": label,
                "defined_by": user,
                "defined_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(tenant_id).write_text(json.dumps(data, indent=2) + "\n")
