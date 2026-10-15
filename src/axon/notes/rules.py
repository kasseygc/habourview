"""High-precision patterns for wording staff use often. Cheap, predictable, and a cross-check on the model.

Rules are written to be precise rather than complete: anything they miss is the model's job.
"""

from __future__ import annotations

import re

from axon.notes.schema import APPLIES_TO, Finding

PATTERNS: dict[tuple[str, str], str] = {
    ("referral", "pending_intake"): r"pending\W+intake not booked|intake not booked",
    ("referral", "waitlisted"): r"wait-?list(?:ed)?|on (?:the )?waitlist|will call when (?:a )?bed opens",
    ("referral", "unreachable"): r"phone disconnected|unable to reach|could not reach|no answer",
    ("referral", "declined"): r"declined (?:assessment|bed offer)|wants outpatient",
    ("referral", "no_show"): r"did not (?:attend|show)|no-show",
    ("referral", "not_appropriate"): r"not appropriate for level of care",
    ("referral", "referred_out"): r"referred out|needs medical detox",
    ("discharge", "self_discharge"): r"\bleft ama\b|self-discharged|left during the night",
    ("discharge", "peer_conflict"): r"conflict w(?:ith|/) (?:a )?peer",
    ("discharge", "rule_violations"): r"repeated rule violations",
    ("discharge", "use_on_premises"): r"use on premises",
    ("discharge", "violence"): r"violence",
    ("discharge", "positive_drug_test"): r"positive ua|positive (?:urine|drug) test",
    ("discharge", "incarceration"): r"incarcerated|outstanding warrant|arrested",
    ("discharge", "transfer_detox"): r"higher level of care|\(detox\)",
    ("discharge", "transfer_hospital"): r"transferred to hospital",
    ("discharge", "moved_region"): r"program in home region",
    ("risk", "low_mood"): r"low mood",
    ("risk", "cravings"): r"(?<!no )(?<!denies )cravings? reported|some cravings",
    ("risk", "incident"): r"\bincident\b",
    ("risk", "substance_use"): r"positive ua|use on premises",
    ("engagement", "attending_groups"): r"attending all groups|engagement in groups|\bNA \d|\bAA \d",
    ("engagement", "sponsor"): r"sponsor identified|has a sponsor|got a sponsor",
    ("engagement", "work"): r"\bemployed\b|job search",
    ("engagement", "aftercare_planned"): r"aftercare plan",
    ("engagement", "aftercare_attending"): r"attending weekly aftercare|aftercare check-in",
    ("engagement", "aftercare_missed"): r"missed (?:last )?\d* ?aftercare",
    ("engagement", "alumni_involved"): r"alumni (?:dinner|nite|night)|volunteers at house",
    ("engagement", "sober_living"): r"sober living",
    ("engagement", "doing_well"): r"doing well|good spirits",
    ("engagement", "no_recent_contact"): r"no contact since",
}
COMPILED = {k: re.compile(v, re.IGNORECASE) for k, v in PATTERNS.items()}


def extract(note: str, status: str) -> list[Finding]:
    fields = APPLIES_TO.get(status, ())
    out = []
    for (field, value), pattern in COMPILED.items():
        if field not in fields:
            continue
        m = pattern.search(note or "")
        if m:
            out.append(Finding(field, value, m.group(0), "rules"))
    return out
