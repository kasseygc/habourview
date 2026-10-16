"""Staff notes -> structured findings with a review status.

Review status:
  agreed        rules and model found the same thing (referral, discharge)
  accepted      engagement found by the model with a valid quote
  needs_review  every risk flag, and anything rules and model disagree on
  rules_only    the model was not run (no recording, no API key); unconfirmed
Recorded fields stay the source of truth. Findings are shown next to them until staff confirm.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from axon.agent.llm import LLMUnavailable, SpecModel
from axon.notes import model as notes_model
from axon.notes import rules
from axon.notes.schema import ALWAYS_REVIEW, NEEDS_AGREEMENT, referral_state
from axon.redact import redact

FINDING_COLUMNS = ["resident_id", "field", "value", "quote", "source", "review"]


@dataclass
class NotesResult:
    findings: pd.DataFrame
    per_resident: pd.DataFrame
    model_ran: bool
    model_calls: int
    rejected: list[dict]


def _review(field: str, sources: set[str], model_ran: bool) -> str:
    if not model_ran:
        return "rules_only"
    if field in ALWAYS_REVIEW:
        return "needs_review"
    if field in NEEDS_AGREEMENT:
        return "agreed" if sources == {"rules", "model"} else "needs_review"
    return "accepted" if "model" in sources else "needs_review"


def run_notes(raw: pd.DataFrame, llm: SpecModel | None, directory: tuple[str, ...] = ()) -> NotesResult:
    """directory: the house's known client and contact names, redacted before anything reads a note."""
    rows = []
    for rid, note, status in zip(raw["resident_id"], raw["staff_note"], raw["current_status"]):
        text = redact((note or "").strip(), directory=directory).text
        rows.append({"resident_id": rid, "note": text, "status": status})

    # One model item per unique (redacted note, status); placeholders and blanks are skipped.
    unique: dict[tuple[str, str], str] = {}
    for r in rows:
        if len(r["note"]) > 3 and (r["note"], r["status"]) not in unique:
            unique[(r["note"], r["status"])] = f"n{len(unique) + 1:03d}"
    items = [{"id": i, "note": n, "status": s} for (n, s), i in sorted(unique.items(), key=lambda kv: kv[1])]

    model_out = None
    if llm is not None and items:
        try:
            model_out = notes_model.run(items, llm)
        except LLMUnavailable:
            model_out = None
    model_ran = model_out is not None

    findings, summary = [], []
    for r in rows:
        found: dict[tuple[str, str], dict] = {}
        for f in rules.extract(r["note"], r["status"]):
            found.setdefault((f.field, f.value), {"quote": f.quote, "sources": set()})["sources"].add("rules")
        item_id = unique.get((r["note"], r["status"]))
        unclear = False
        if model_ran and item_id:
            for f in model_out.findings.get(item_id, []):
                entry = found.setdefault((f.field, f.value), {"quote": f.quote, "sources": set()})
                entry["sources"].add("model")
                entry["quote"] = f.quote
            unclear = model_out.unclear.get(item_id, False)
        for (field, value), e in sorted(found.items()):
            findings.append({
                "resident_id": r["resident_id"], "field": field, "value": value, "quote": e["quote"],
                "source": "+".join(sorted(e["sources"])), "review": _review(field, e["sources"], model_ran),
            })
        referral = next((v for (f, v) in sorted(found) if f == "referral"), None)
        summary.append({
            "resident_id": r["resident_id"],
            "note_referral": referral,
            "note_referral_state": referral_state(referral),
            "note_discharge": ", ".join(v for (f, v) in sorted(found) if f == "discharge") or None,
            "note_unclear": unclear,
        })
    return NotesResult(
        findings=pd.DataFrame(findings, columns=FINDING_COLUMNS),
        per_resident=pd.DataFrame(summary),
        model_ran=model_ran,
        model_calls=model_out.calls if model_out else 0,
        rejected=model_out.rejected if model_out else [],
    )
