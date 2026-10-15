"""Words that sound like metrics but have no single meaning (D-13).

Each term lists the questions we ask and the concrete, catalogue-backed choices offered.
Choices are never invented by the LLM. A chosen definition is saved for the house and
applied deterministically to every later spec that uses the word.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Choice:
    id: str
    label: str
    patch: dict  # fields forced onto the spec: metric, filters (merged by field), group_by


@dataclass(frozen=True)
class Term:
    id: str
    pattern: re.Pattern[str]
    question: str
    why: str
    choices: tuple[Choice, ...] = field(default_factory=tuple)


def _p(words: str) -> re.Pattern[str]:
    return re.compile(rf"\b(?:{words})\b", re.IGNORECASE)


GLOSSARY: dict[str, Term] = {
    t.id: t
    for t in [
        Term(
            "sober",
            _p(r"sober|sobriety|clean|abstinent|abstinence|drug[- ]free|substance[- ]free"),
            "What should 'sober' mean here?",
            "Sobriety isn't recorded. Follow-ups record 'engaged in recovery', 'relapse reported', "
            "or that the person couldn't be reached.",
            (
                Choice("engaged_6m", "Engaged in recovery at the 6-month follow-up, out of everyone due "
                       "(people we couldn't reach are not counted as sober)",
                       {"metric": "followup_engaged_rate", "filters": [{"field": "horizon", "values": ["6m"]}]}),
                Choice("engaged_12m", "Engaged in recovery at the 12-month follow-up, out of everyone due",
                       {"metric": "followup_engaged_rate", "filters": [{"field": "horizon", "values": ["12m"]}]}),
                Choice("all_6m", "Don't pick one number: show every 6-month outcome",
                       {"metric": "followup_outcomes", "filters": [{"field": "horizon", "values": ["6m"]}],
                        "group_by": ["outcome"]}),
            ),
        ),
        Term(
            "relapse",
            _p(r"relapse[sd]?|relapsing|using again|went back to using"),
            "What should 'relapse' mean here?",
            "'Relapse reported' is a follow-up result. Relapses during a stay are only in staff notes, "
            "which the agent can't read.",
            (
                Choice("relapse_6m", "Relapse reported at the 6-month follow-up, out of everyone due",
                       {"metric": "followup_outcomes", "filters": [{"field": "horizon", "values": ["6m"]}],
                        "group_by": ["outcome"]}),
                Choice("relapse_12m", "Relapse reported at the 12-month follow-up, out of everyone due",
                       {"metric": "followup_outcomes", "filters": [{"field": "horizon", "values": ["12m"]}],
                        "group_by": ["outcome"]}),
            ),
        ),
        Term(
            "successful",
            _p(r"success(?:ful|fully)?|succeed(?:ed)?|good outcomes?|did well"),
            "What should 'successful' mean here?",
            "Success could mean finishing the program or how someone is doing after they leave.",
            (
                Choice("completed_program", "Completed the program (discharge reason 'completed'), out of everyone who left",
                       {"metric": "discharges", "group_by": ["completion_group"]}),
                Choice("engaged_6m", "Engaged in recovery at the 6-month follow-up, out of everyone due",
                       {"metric": "followup_engaged_rate", "filters": [{"field": "horizon", "values": ["6m"]}]}),
            ),
        ),
        Term(
            "active",
            _p(r"active|current(?:ly)? (?:residents?|clients?)|on the books"),
            "Who counts as 'active'?",
            "Some houses count only people living in the house; others include people in aftercare.",
            (
                Choice("in_house", "Living in the house now (phases 1 to 3)",
                       {"metric": "residents_now",
                        "filters": [{"field": "current_status", "values": ["phase_1", "phase_2", "phase_3"]}]}),
                Choice("in_house_or_aftercare", "Living in the house or in aftercare",
                       {"metric": "residents_now",
                        "filters": [{"field": "current_status", "values": ["phase_1", "phase_2", "phase_3", "aftercare"]}]}),
            ),
        ),
        Term(
            "this_year",
            _p(r"this year|so far this year|year[- ]to[- ]date|ytd"),
            "Which year do you mean?",
            "The data runs to 15 January 2026, so 'this year' has only two weeks of data.",
            (
                Choice("fy2025", "FY2025 (January to December 2025, the last full fiscal year)",
                       {"time_window": {"preset": "fy2025", "start": None, "end": None}}),
                Choice("fy2026_to_date", "FY2026 so far (1 to 15 January 2026)",
                       {"time_window": {"preset": "custom", "start": "2026-01-01", "end": "2026-01-15"}}),
            ),
        ),
        Term(
            "dropout",
            _p(r"drop(?:ped)?[- ]?outs?|dropped|quit|left early|walked out"),
            "Which departures count as dropping out?",
            "People leave early for different reasons, and only some are the resident's own choice.",
            (
                Choice("self_only", "Self-discharge only (the resident chose to leave)",
                       {"metric": "discharges", "filters": [{"field": "discharge_reason", "values": ["self_discharge"]}]}),
                Choice("self_or_admin", "Self-discharge or administrative discharge",
                       {"metric": "discharges",
                        "filters": [{"field": "discharge_reason", "values": ["self_discharge", "administrative"]}]}),
                Choice("all_early", "Any departure before completing (includes transfers)",
                       {"metric": "discharges", "filters": [{"field": "completion_group", "values": ["early_leaver"]}]}),
            ),
        ),
    ]
}


def find_terms(text: str) -> list[str]:
    """Glossary terms used in the text, in order of first appearance."""
    hits = [(m.start(), tid) for tid, t in GLOSSARY.items() if (m := t.pattern.search(text))]
    return [tid for _, tid in sorted(hits)]
