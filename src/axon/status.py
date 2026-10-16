"""The status strip: four operational facts for today.

Shown as neutral numbers. Red is reserved for a real breach in recorded data (more residents than
beds); nothing here is a warning about data quality, which the dashboard is not for.
"Waiting for intake" is the one place staff notes change a number: referrals the notes say are
closed are reported beside the count (AI-assisted), and drop out of it once staff confirm.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from axon.warehouse import Warehouse

STATUS_ICON = {"red": "error", "neutral": "info"}


@dataclass(frozen=True)
class Flag:
    key: str
    label: str
    value: str
    status: str  # neutral | red
    detail: str
    badge: str | None = None  # only for red


def board(w: Warehouse, decisions: dict[str, str] | None = None) -> list[Flag]:
    """decisions: staff confirmations of note findings (see axon.notes.review)."""
    decisions = decisions or {}
    r, f = w.residents, w.followups
    as_of = pd.Timestamp(w.as_of)
    cap = w.capacity
    in_house = int(r["in_residence"].sum())

    not_yet = r[~r["matured"] & (r["stage"] == "referred")]
    closed_by_note = not_yet["note_referral_state"].eq("closed")
    confirmed = not_yet.apply(
        lambda x: decisions.get(f"{x.resident_id}|referral|{x.note_referral}") == "confirm", axis=1
    ) if len(not_yet) else pd.Series(dtype=bool)
    waiting = not_yet[~(closed_by_note & confirmed)]
    unconfirmed_closed = int((closed_by_note & ~confirmed).sum())
    still_open = len(waiting) - unconfirmed_closed

    upcoming = f[~f["is_due"] & f["due_date"].between(as_of, as_of + pd.Timedelta(days=30), inclusive="right")]
    by_h = upcoming.groupby("horizon_months").size().to_dict()
    missing = int((f["is_due"] & (f["outcome"] == "not_recorded")).sum())

    flags = [
        Flag("beds", "In the house tonight", f"{in_house} / {cap}", "red" if in_house > cap else "neutral",
             f"{in_house - cap} more residents than beds" if in_house > cap else f"{cap - in_house} beds open",
             "Over capacity" if in_house > cap else None),
        Flag("waiting", "Waiting for intake", str(len(waiting)), "neutral",
             f"notes say {unconfirmed_closed} closed, {still_open} open" if unconfirmed_closed
             else f"referred in the last {(as_of - r.loc[~r['matured'], 'referral_date'].min()).days if (~r['matured']).any() else 0} days"),
        Flag("calls", "Follow-up calls, next 30 days", str(len(upcoming)), "neutral",
             f"{by_h.get(6, 0)} at 6 months, {by_h.get(12, 0)} at 12 months"),
        Flag("missing", "Follow-ups due, not recorded", str(missing), "neutral", "date passed, no result entered"),
    ]
    return flags


def review_queue(w: Warehouse, decisions: dict[str, str] | None = None) -> pd.DataFrame:
    """Findings that need a person: every risk flag, and referral or discharge findings not agreed by
    both rules and model. Engagement is low-stakes and only queued when the model didn't confirm it."""
    decisions = decisions or {}
    f = w.note_findings
    if f.empty:
        return f
    needs = f["review"].isin(["needs_review", "rules_only"]) & ~((f["field"] == "engagement") & (f["review"] == "rules_only"))
    q = f[needs].copy()
    q["key"] = q["resident_id"] + "|" + q["field"] + "|" + q["value"]
    q = q[~q["key"].isin(decisions)]
    order = {"risk": 0, "referral": 1, "discharge": 2, "engagement": 3}
    return q.sort_values(by=["field", "resident_id"], key=lambda c: c.map(order) if c.name == "field" else c)
