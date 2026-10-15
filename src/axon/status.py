"""The status board: what is happening now and what needs doing (D-23).

Each flag has a value, a status (red / amber / green) and a next step. Status colours are
semantic and always shown with an icon and a label:
  red    a hard breach (more residents than beds)
  amber  needs attention (missing entries, data problems, people waiting longer than usual)
  green  within the normal range
Thresholds come from the house's own data where possible (for example, the usual wait is the
90th percentile of referral-to-intake days), never from an invented target.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from axon.stats import summarize
from axon.warehouse import Warehouse

STATUS_ICON = {"red": "error", "amber": "warning", "green": "check_circle"}


@dataclass(frozen=True)
class Flag:
    key: str
    label: str
    value: str
    status: str  # red | amber | green
    badge: str  # short status label shown next to the icon
    detail: str
    action: str | None = None


def board(w: Warehouse) -> list[Flag]:
    r, f, census = w.residents, w.followups, w.nightly_census
    as_of = pd.Timestamp(w.as_of)
    cap = w.capacity
    in_house = int(r["in_residence"].sum())
    open_beds = cap - in_house

    waiting = r[~r["matured"] & (r["stage"] == "referred")]
    days_waiting = (as_of - waiting["referral_date"]).dt.days
    usual = summarize(r.loc[r["matured"], "days_referral_to_intake"]).p90 or 0
    long_waits = int((days_waiting > usual).sum())

    upcoming = f[~f["is_due"] & f["due_date"].between(as_of, as_of + pd.Timedelta(days=30), inclusive="right")]
    missing = int((f["is_due"] & (f["outcome"] == "not_recorded")).sum())
    issues = w.dq_issues
    over_capacity_nights = int((census["residents"] > cap).sum())
    # Red only when recorded dates alone exceed capacity; nights pushed over by estimates are amber.
    recorded_over = int(((census["residents"] - census["residents_estimated"]) > cap).sum())

    flags = []
    if in_house > cap:
        beds = Flag("beds", "In the house tonight", f"{in_house} / {cap}", "red", "Over capacity",
                    f"{in_house - cap} more residents than beds", "Check discharge dates and bed assignments")
    elif open_beds > 0 and len(waiting) > 0:
        beds = Flag("beds", "In the house tonight", f"{in_house} / {cap}", "amber", "Beds open",
                    f"{open_beds} beds open while {len(waiting)} referrals wait", "Book intakes for waiting referrals")
    else:
        beds = Flag("beds", "In the house tonight", f"{in_house} / {cap}", "green", "Normal",
                    f"{open_beds} beds open")
    flags.append(beds)

    if long_waits:
        flags.append(Flag("waiting", "Waiting for intake", str(len(waiting)), "amber", "Waiting long",
                          f"{long_waits} waiting longer than usual ({usual:.0f}+ days)", "Follow up on the oldest referrals"))
    else:
        flags.append(Flag("waiting", "Waiting for intake", str(len(waiting)), "green", "Normal",
                          f"none waiting longer than {usual:.0f} days"))

    by_h = upcoming.groupby("horizon_months").size().to_dict()
    flags.append(Flag("calls", "Follow-up calls, next 30 days", str(len(upcoming)), "green", "Scheduled",
                      f"{by_h.get(6, 0)} at 6 months, {by_h.get(12, 0)} at 12 months"))

    if missing:
        flags.append(Flag("missing", "Outcomes not recorded", str(missing), "amber", "Needs entry",
                          "follow-up date passed, no result entered", "Enter the missing results"))
    else:
        flags.append(Flag("missing", "Outcomes not recorded", "0", "green", "Up to date", "every due result entered"))

    n_res = issues.loc[issues["resident_id"] != "(house)", "resident_id"].nunique()
    if len(issues):
        detail = f"{len(issues)} issues across {n_res} records"
        if over_capacity_nights:
            detail += f"; {over_capacity_nights} nights over capacity" + ("" if recorded_over else " (from estimated dates)")
        flags.append(Flag("data", "Records to fix", str(len(issues)), "red" if recorded_over else "amber",
                          "Needs review", detail, "Open the Data quality tab"))
    else:
        flags.append(Flag("data", "Records to fix", "0", "green", "Clean", "no rule broken"))
    return flags
