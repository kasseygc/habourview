"""Rule-based PHI redaction for staff notes and for questions typed into the agent (D-17).

Prototype scope: structured identifiers (phones, emails, health-card numbers, SINs, dates,
resident IDs) and names that follow a relationship or role word ("brother Kevin",
"probation officer J. Martel", "Mom (Linda)"). Production would add a self-hosted
named-entity model (e.g. Microsoft Presidio) and the house's own directory of client and
contact names, with human spot-checks (see WRITEUP.md, C2).

Only the types of what was found are logged, never the values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

RELATIONS = (
    r"brother|sister|mom|mother|dad|father|son|daughter|wife|husband|partner|girlfriend|boyfriend|"
    r"aunt|uncle|cousin|grandmother|grandfather|grandma|grandpa|friend|sponsor|guardian|"
    r"probation officer|parole officer|officer|caseworker|case worker|case manager|youth worker|social worker|"
    r"counsellor|counselor|worker|lawyer|dr\.?|doctor|nurse"
)
NAME = r"(?:[A-Z]\.\s?)*[A-Z][a-z'\-]+(?:\s(?:[A-Z]\.\s?)*[A-Z][a-z'\-]+)?"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")),
    ("HEALTH_CARD", re.compile(r"\b\d{4}[\s-]?\d{3}[\s-]?\d{3}[\s-]?[A-Z]{2}\b")),
    ("SIN", re.compile(r"\b\d{3}[\s-]\d{3}[\s-]\d{3}\b")),
    ("DATE", re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b")),
    ("RESIDENT_ID", re.compile(r"\b[A-Z]{2,3}-\d{3,5}\b")),
]
# Relationship words match in any case; names must be capitalised ("Sister Priya", not "sister dropped").
RELATION_NAME = re.compile(rf"\b(?P<rel>(?i:{RELATIONS}))(?P<sep>\s*\(?\s*)(?P<name>{NAME})")
NAME_POSSESSIVE = re.compile(rf"\b(?P<name>[A-Z][a-z\-]+)(?P<rest>'s\s+(?i:{RELATIONS})\b)")

# Capitalised words after a relationship word that are not names.
NOT_NAMES = {"Called", "Dropped", "Visited", "Asked", "Said", "Came", "Will", "Is", "Was", "Has", "And", "To", "Re"}


@dataclass
class Redaction:
    text: str
    found: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.found)


def redact(text: str | None, *, keep_dates: bool = False) -> Redaction:
    """Replace identifiers with [TYPE] tags.

    keep_dates=True is used for questions typed into the agent: "since 2025-03-01" is a filter, not PHI.
    """
    if not text:
        return Redaction(text or "")
    out = text
    found: list[str] = []
    for kind, pattern in PATTERNS:
        if keep_dates and kind == "DATE":
            continue
        out, n = pattern.subn(f"[{kind}]", out)
        found += [kind] * n

    def _name(m: re.Match[str]) -> str:
        name = m.group("name")
        if not name[0].isupper() or name.split()[0] in NOT_NAMES:
            return m.group(0)
        found.append("NAME")
        return f"{m.group('rel')}{m.group('sep')}[NAME]"

    def _possessive(m: re.Match[str]) -> str:
        found.append("NAME")
        return f"[NAME]{m.group('rest')}"

    out = RELATION_NAME.sub(_name, out)
    out = NAME_POSSESSIVE.sub(_possessive, out)
    return Redaction(out, found)
