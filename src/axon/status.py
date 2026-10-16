"""The status strip: four operational facts for today.

Shown as neutral numbers. Red is reserved for a real breach in recorded data (more residents than
beds); nothing here is a warning about data quality, which the dashboard is not for.
Every headline number comes from recorded fields. Staff notes only add the split under "new
referrals" (still waiting or closed), marked as AI-assisted.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from axon.config import MATURITY_DAYS
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
    tip: str | None = None


def board(w: Warehouse) -> list[Flag]:
    r, f = w.residents, w.followups
    as_of = pd.Timestamp(w.as_of)
    cap = w.capacity
    in_house = int(r["in_residence"].sum())

    # New referrals with no intake recorded: a recorded fact. Whether each is still waiting is only
    # in the staff notes, so the notes give the split underneath, never the headline.
    no_intake = r["stage"] == "referred"
    recent = r[~r["matured"] & no_intake]
    state = recent["note_referral_state"]
    n_open, n_closed = int(state.eq("open").sum()), int(state.eq("closed").sum())
    n_unread = len(recent) - n_open - n_closed
    older_open = int((r["matured"] & no_intake & r["note_referral_state"].eq("open")).sum())
    waiting_tip = (f"Referred in the last {MATURITY_DAYS} days, with no intake recorded. Waiting or closed comes from "
                   "the staff notes, read by rules and a self-hosted model (AI-assisted, not confirmed by staff).")
    if older_open:
        waiting_tip += (f" {older_open} older referrals still have notes saying pending intake; "
                        "those notes are probably out of date.")

    upcoming = f[~f["is_due"] & f["due_date"].between(as_of, as_of + pd.Timedelta(days=30), inclusive="right")]
    by_h = upcoming.groupby("horizon_months").size().to_dict()
    missing = int((f["is_due"] & (f["outcome"] == "not_recorded")).sum())

    flags = [
        Flag("beds", "In the house tonight", f"{in_house} / {cap}", "red" if in_house > cap else "neutral",
             f"{in_house - cap} more residents than beds" if in_house > cap else f"{cap - in_house} beds open",
             "Over capacity" if in_house > cap else None),
        Flag("waiting", f"New referrals, last {MATURITY_DAYS} days", str(len(recent)), "neutral",
             f"{n_open} waiting, {n_closed} closed (staff notes)" + (f", {n_unread} no usable note" if n_unread else ""),
             tip=waiting_tip),
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
