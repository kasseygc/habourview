"""Structured fields from staff notes, as metrics: who has what, out of whom.

Counts people (not notes) per category inside the group the field applies to, so every number
has its denominator. Values are AI-assisted (rules plus a self-hosted model) and labelled so.
Groups about people who left or referrals not admitted follow the fiscal year (by discharge or
referral date); groups defined by where people are now don't.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from axon.config import FiscalYear
from axon.notes.schema import FIELDS

# (name, who, fields, date that places them in a fiscal year; None = where people are now)
GROUPS = [
    ("In the house now", lambda r: r["in_residence"], ("passes", "engagement", "risk"), None),
    ("Aftercare and alumni", lambda r: r["current_status"].isin(["aftercare", "alumni"]), ("engagement", "destination", "risk"), None),
    ("Left early", lambda r: r["current_status"] == "discharged", ("discharge", "destination"), "discharge_date"),
    ("Referred, not admitted", lambda r: r["current_status"] == "not_admitted", ("referral",), "referral_date"),
]


@dataclass
class GroupSummary:
    name: str
    by_year: bool  # False: where people are now, whatever the fiscal year
    people: int
    with_finding: int
    table: pd.DataFrame  # field, value, people, share


def summarize(residents: pd.DataFrame, findings: pd.DataFrame, fy: FiscalYear | None = None) -> list[GroupSummary]:
    out = []
    for name, pick, fields, date_col in GROUPS:
        mask = pick(residents)
        if fy is not None and date_col is not None:
            mask &= residents[date_col].between(pd.Timestamp(fy.start), pd.Timestamp(fy.end))
        ids = set(residents.loc[mask, "resident_id"])
        f = findings[findings["resident_id"].isin(ids) & findings["field"].isin(fields)]
        counts = f.groupby(["field", "value"])["resident_id"].nunique().rename("people").reset_index()
        order = {(fl, v): i for i, (fl, v) in enumerate((fl, v) for fl in fields for v in FIELDS[fl])}
        counts["order"] = [order.get((a, b), 999) for a, b in zip(counts["field"], counts["value"])]
        counts = counts.sort_values("order").drop(columns="order")
        counts["share"] = counts["people"] / max(len(ids), 1)
        out.append(GroupSummary(name, date_col is not None, len(ids), f["resident_id"].nunique(), counts.reset_index(drop=True)))
    return out


def headline(residents: pd.DataFrame, findings: pd.DataFrame) -> dict[str, tuple[int, int]]:
    """The four examples the brief names, for people in the house now: (people with it, people in the house)."""
    ids = set(residents.loc[residents["in_residence"], "resident_id"])
    f = findings[findings["resident_id"].isin(ids)]

    def n(mask) -> int:
        return f.loc[mask, "resident_id"].nunique()

    return {
        "Meetings or groups": (n(f["value"] == "attending_groups"), len(ids)),
        "Passes mentioned": (n(f["field"] == "passes"), len(ids)),
        "Incidents": (n(f["value"] == "incident"), len(ids)),
        "Mood or risk flags": (n((f["field"] == "risk") & (f["value"] != "incident")), len(ids)),
    }
