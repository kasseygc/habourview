"""Claude reads redacted notes and fills the fixed schema, quoting its evidence (D-24).

Guardrails:
- the model sees only the redacted note and which fields apply; never a name, ID or date of birth
- every finding must quote the note; a quote that is not in the note is rejected
- values come from enums, and a field that does not apply to the person is rejected
Notes are sent in batches of unique (note, status group) pairs, so 200 residents need only a few calls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from axon.agent.llm import LLMUnavailable, SpecModel
from axon.notes.schema import APPLIES_TO, FIELDS, Finding

BATCH_SIZE = 25

SYSTEM = """You read short notes written by staff at a residential recovery home and record only what
each note states, using the fixed fields below. Your output is checked by code and reviewed by staff.

Rules:
- Use only the fields listed as allowed for that note. They depend on where the person is.
- Every finding needs a quote: the exact words from the note that support it, copied exactly.
- Record only what is stated. Do not infer. A negation is not a finding ("denies cravings" is not cravings).
- Names, phone numbers and contact requests are not findings. Notes are redacted: [NAME], [PHONE] and
  similar tags are placeholders.
- If a note is too vague to say anything ("see file", "N/A", "no change"), return no findings.
- If a note could mean two different things, set unclear to true and return only what is certain.

Fields and values:
""" + "\n".join(
    f"- {f}:\n" + "\n".join(f"    {v}: {d}" for v, d in values.items()) for f, values in FIELDS.items()
)


def json_schema() -> dict:
    all_values = sorted({v for values in FIELDS.values() for v in values})
    finding = {
        "type": "object",
        "properties": {
            "field": {"type": "string", "enum": list(FIELDS)},
            "value": {"type": "string", "enum": all_values},
            "quote": {"type": "string"},
        },
        "required": ["field", "value", "quote"],
        "additionalProperties": False,
    }
    note = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "findings": {"type": "array", "items": finding},
            "unclear": {"type": "boolean"},
        },
        "required": ["id", "findings", "unclear"],
        "additionalProperties": False,
    }
    return {"type": "object", "properties": {"notes": {"type": "array", "items": note}},
            "required": ["notes"], "additionalProperties": False}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


@dataclass
class ModelOutput:
    findings: dict[str, list[Finding]] = field(default_factory=dict)  # item id -> findings
    unclear: dict[str, bool] = field(default_factory=dict)
    rejected: list[dict] = field(default_factory=list)  # findings that failed validation
    calls: int = 0
    mode: str = ""


def validate(item: dict, raw_findings: list[dict]) -> tuple[list[Finding], list[dict]]:
    allowed = APPLIES_TO.get(item["status"], ())
    ok, bad = [], []
    note = _norm(item["note"])
    for f in raw_findings:
        problem = None
        if f["field"] not in allowed:
            problem = "field does not apply to this person"
        elif f["value"] not in FIELDS[f["field"]]:
            problem = "value does not belong to the field"
        elif not f["quote"].strip() or _norm(f["quote"]) not in note:
            problem = "quote is not in the note"
        if problem:
            bad.append({**f, "id": item["id"], "problem": problem})
        else:
            ok.append(Finding(f["field"], f["value"], f["quote"], "model"))
    return ok, bad


def run(items: list[dict], llm: SpecModel) -> ModelOutput:
    """items: [{"id", "note" (redacted), "status"}]. Raises LLMUnavailable if the model can't be reached."""
    out = ModelOutput()
    system = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
    schema = json_schema()
    by_id = {i["id"]: i for i in items}
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        payload = [{"id": i["id"], "allowed_fields": list(APPLIES_TO.get(i["status"], ())), "note": i["note"]} for i in batch]
        call = llm.complete(system, json.dumps(payload, ensure_ascii=False, indent=1), schema)
        out.calls += 1
        out.mode = call.mode
        data = json.loads(call.text)
        for n in data.get("notes", []):
            item = by_id.get(n["id"])
            if item is None:
                out.rejected.append({"id": n["id"], "problem": "unknown note id"})
                continue
            ok, bad = validate(item, n["findings"])
            out.findings[n["id"]] = ok
            out.unclear[n["id"]] = bool(n["unclear"])
            out.rejected += bad
    return out


__all__ = ["run", "validate", "json_schema", "ModelOutput", "LLMUnavailable"]
