"""PHI redaction for staff notes and for questions typed into the agent.

Four layers, in order, each replacing what it finds with a [TYPE] tag:
1. Structured identifiers: phones, emails, health-card numbers, SINs, dates, resident IDs.
2. Names next to a relationship or role word: "brother Kevin", "PO Martel", "Mom (Linda)",
   "Linda (sister)", "Kevin's brother".
3. The house's directory: names the case-management system already knows (clients and contacts).
4. A self-hosted name detector (spaCy, runs on this machine; nothing is sent anywhere) for names with
   no context, such as "Called Kevin". Only proper-noun words inside a detected name are replaced,
   and words the notes need (NA, AA, SMART, weekdays) are never replaced.
Over-redaction is the safe failure: a lost word costs a finding, a missed name costs privacy.

Only the types of what was found are logged, never the values. The detector model is set by
AXON_NAME_MODEL: default en_core_web_lg, chosen over the small model on eval/REDACTION_REPORT.md;
"none" turns it off, for testing the other layers alone.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache

RELATIONS = (
    r"brother|sister|mom|mother|dad|father|son|daughter|wife|husband|partner|girlfriend|boyfriend|"
    r"aunt|uncle|cousin|grandmother|grandfather|grandma|grandpa|friend|sponsor|guardian|"
    r"probation officer|parole officer|officer|caseworker|case worker|case manager|youth worker|social worker|"
    r"counsellor|counselor|worker|lawyer|dr\.?|doctor|nurse|po|sw|cw|mr\.?|mrs\.?|ms\.?"
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
RELATION_NAME = re.compile(rf"\b(?P<rel>(?i:{RELATIONS}))(?P<sep>\s*[(,]?\s*)(?P<name>{NAME})")
NAME_POSSESSIVE = re.compile(rf"\b(?P<name>[A-Z][a-z\-]+)(?P<rest>'s\s+(?i:{RELATIONS})\b)")
NAME_THEN_RELATION = re.compile(rf"\b(?P<name>[A-Z][a-z\-]+)(?P<rest>\s*\((?i:{RELATIONS})\))")

# Capitalised words after a relationship word that are not names.
NOT_NAMES = {"Called", "Dropped", "Visited", "Asked", "Said", "Came", "Will", "Is", "Was", "Has", "And", "To", "Re",
             "Requested", "Attended", "Notified", "Confirmed"}

# Words staff notes and questions need, which a name detector can mistake for names.
KEEP = {
    "na", "aa", "ca", "smart", "recovery", "res", "client", "resident", "phone", "staff", "group", "intake",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "mon", "tue", "tues", "wed",
    "thu", "thurs", "fri", "sat", "sun", "good", "will", "hope", "grace", "faith", "camh", "cas", "ontario", "works",
    "salvation", "army", "detox", "aftercare", "phase", "fy2024", "fy2025", "q1", "q2", "q3", "q4", "axon",
    "harbourview", "house", "tim", "hortons", "vm", "pm", "am", "ama", "ua",
}

# Relationship and role words are never names, even when a detector thinks so ("Mom, Debbie").
RELATION_WORDS = {w.replace("\\", "").rstrip(".?") for w in RELATIONS.split("|") if " " not in w}

DEFAULT_MODEL = os.environ.get("AXON_NAME_MODEL", "en_core_web_lg")


@dataclass
class Redaction:
    text: str
    found: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.found)


@lru_cache(maxsize=2)
def _nlp(model: str):
    import spacy

    # Only what name detection needs: tokens, part-of-speech tags and entities.
    return spacy.load(model, exclude=["parser", "lemmatizer", "senter"])


def _directory_pattern(directory: Iterable[str]) -> re.Pattern[str] | None:
    words = sorted({w for name in directory for w in re.findall(r"[A-Z][a-z'\-]+", name) if w.lower() not in KEEP},
                   key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + r")\b") if words else None


def _detect(text: str, model: str) -> list[tuple[int, int]]:
    """Character spans of proper-noun words inside detected person names."""
    spans = []
    for ent in _nlp(model)(text).ents:
        if ent.label_ != "PERSON":
            continue
        for tok in ent:
            word = tok.text.lower().strip(".")
            if tok.pos_ == "PROPN" and tok.text[:1].isupper() and word not in KEEP and word not in RELATION_WORDS \
                    and not tok.text.startswith("["):
                spans.append((tok.idx, tok.idx + len(tok.text)))
    return spans


def redact(text: str | None, *, keep_dates: bool = False, directory: Iterable[str] = (),
           model: str | None = DEFAULT_MODEL) -> Redaction:
    """Replace identifiers and names with [TYPE] tags.

    keep_dates=True is used for questions typed into the agent: "since 2025-03-01" is a filter, not PHI.
    directory: the house's known client and contact names. model: the name detector, or None/"none".
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
        if not name[0].isupper() or name.split()[0] in NOT_NAMES or name.lower() in KEEP:
            return m.group(0)
        found.append("NAME")
        return f"{m.group('rel')}{m.group('sep')}[NAME]"

    def _before(m: re.Match[str]) -> str:
        if m.group("name").lower() in KEEP:
            return m.group(0)
        found.append("NAME")
        return f"[NAME]{m.group('rest')}"

    out = RELATION_NAME.sub(_name, out)
    out = NAME_POSSESSIVE.sub(_before, out)
    out = NAME_THEN_RELATION.sub(_before, out)

    known = _directory_pattern(directory)
    if known is not None:
        out, n = known.subn("[NAME]", out)
        found += ["NAME"] * n

    if model and model != "none":
        for start, end in sorted(_detect(out, model), reverse=True):
            out = out[:start] + "[NAME]" + out[end:]
            found.append("NAME")

    out = re.sub(r"\[NAME\](?:\s+\[NAME\])+", "[NAME]", out)  # "Sarah Thompson" is one name
    return Redaction(out, found)
