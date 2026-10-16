"""What can be taken from a staff note, and for whom.

Which fields apply depends on where the person is: a referral that was never admitted can only
yield a referral status; someone in the house can yield risk flags and engagement; someone who
left early can yield discharge details. This keeps extraction focused and stops, for example,
a past incident being raised as a current risk.
"""

from __future__ import annotations

from dataclasses import dataclass

FIELDS: dict[str, dict[str, str]] = {
    "referral": {
        "pending_intake": "intake not booked or scheduled yet; still open",
        "waitlisted": "assessed or accepted, waiting for a bed; still open",
        "unreachable": "could not contact the person (phone disconnected, no answer)",
        "declined": "the person declined assessment or a bed, or chose another program",
        "no_show": "did not attend an intake, assessment or admission",
        "not_appropriate": "assessed as not appropriate for this level of care",
        "referred_out": "sent elsewhere first, for example medical detox",
    },
    "discharge": {
        "self_discharge": "left by their own choice, including against advice or overnight",
        "peer_conflict": "conflict with another resident",
        "rule_violations": "repeated rule violations",
        "use_on_premises": "substance use on the premises",
        "violence": "violence or the violence policy",
        "positive_drug_test": "positive urine or drug test",
        "incarceration": "arrested, incarcerated or held on a warrant",
        "transfer_detox": "moved to detox or a higher level of care",
        "transfer_hospital": "moved to hospital for medical care",
        "moved_region": "moved to a program in another region",
    },
    "risk": {
        "low_mood": "low mood, hopelessness, tearfulness",
        "cravings": "cravings or urges to use (not when denied)",
        "incident": "an incident, altercation or rule breach in the house",
        "substance_use": "use or a positive test while in the program",
    },
    "engagement": {
        "attending_groups": "attending groups or mutual-help meetings (NA, AA)",
        "sponsor": "has or found a sponsor",
        "work": "employed or looking for work",
        "aftercare_planned": "aftercare plan discussed or made",
        "aftercare_attending": "attending aftercare or check-ins",
        "aftercare_missed": "missing aftercare sessions",
        "alumni_involved": "alumni events or volunteering",
        "doing_well": "described as doing well or in good spirits",
        "no_recent_contact": "no contact for a while",
    },
    "passes": {
        "pass_taken": "went out on a day, overnight or weekend pass (approved or planned alone is not taken)",
        "pass_returned": "came back from a pass as expected",
        "pass_late_or_missed": "came back late from a pass, or did not come back",
    },
    "destination": {
        "sober_living": "moved to sober living or supportive housing",
        "home_or_family": "went home or to live with family",
        "another_program": "went to another program or region",
        "detox": "went to detox or a higher level of care",
        "hospital": "went to hospital",
        "custody": "went into custody (arrested, incarcerated)",
    },
}

APPLIES_TO: dict[str, tuple[str, ...]] = {
    "not_admitted": ("referral",),
    "phase_1": ("risk", "engagement", "passes"),
    "phase_2": ("risk", "engagement", "passes"),
    "phase_3": ("risk", "engagement", "passes"),
    "aftercare": ("risk", "engagement", "destination"),
    "alumni": ("engagement", "destination"),
    "discharged": ("discharge", "destination"),
}

OPEN_REFERRAL = {"pending_intake", "waitlisted"}
# Review policy: risk always goes to a person; referral and discharge change reported numbers,
# so they are agreed only when rules and model match; engagement from the model is accepted.
ALWAYS_REVIEW = {"risk"}
NEEDS_AGREEMENT = {"referral", "discharge", "destination"}


NOTES_DISCLOSURE = ("Read from redacted staff notes with AI assistance (a self-hosted model plus rules). "
                    "Not used in funder figures until a staff member confirms it.")


@dataclass(frozen=True)
class Finding:
    field: str
    value: str
    quote: str
    source: str  # rules | model


def referral_state(value: str | None) -> str | None:
    if value is None:
        return None
    return "open" if value in OPEN_REFERRAL else "closed"


LABELS: dict[str, str] = {
    "pending_intake": "pending intake", "waitlisted": "waitlisted", "unreachable": "unreachable",
    "declined": "declined", "no_show": "no-show", "not_appropriate": "not appropriate",
    "referred_out": "referred out", "self_discharge": "left by choice", "peer_conflict": "conflict with a peer",
    "rule_violations": "rule violations", "use_on_premises": "use on premises", "violence": "violence",
    "positive_drug_test": "positive drug test", "incarceration": "incarceration", "transfer_detox": "to detox",
    "transfer_hospital": "to hospital", "moved_region": "moved region", "low_mood": "low mood",
    "cravings": "cravings", "incident": "incident", "substance_use": "substance use",
    "attending_groups": "attending groups", "sponsor": "sponsor", "work": "work or job search",
    "aftercare_planned": "aftercare planned", "aftercare_attending": "attending aftercare",
    "aftercare_missed": "missing aftercare", "alumni_involved": "alumni involvement", "sober_living": "sober living",
    "doing_well": "doing well", "no_recent_contact": "no recent contact", "no usable note": "no usable note",
    "open": "open", "closed": "closed", "pass_taken": "pass taken", "pass_returned": "back from pass",
    "pass_late_or_missed": "late or missed return", "home_or_family": "home or family",
    "another_program": "another program", "detox": "detox", "hospital": "hospital", "custody": "custody",
    "not stated": "not stated", "completed": "completed", "left_by_choice": "left by choice",
    "discharged_by_house": "discharged by the house", "transferred": "transferred",
    "other_or_unknown": "other or unknown", "still_in_program": "still in the program",
}


def label(value: str) -> str:
    return LABELS.get(value, value.replace("_", " "))
