"""Build the derived tables that both the dashboard and the agent read.

This is the single place where metric definitions turn into data:

* ``residents``      one row per referral, with stage flags, timings and fiscal years
* ``followups``      one row per resident per follow-up horizon (6 and 12 months)
* ``nightly_census`` one row per night: how many beds were occupied

Staff notes are deliberately not carried into any of these tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from axon.config import AS_OF, FOLLOWUP_HORIZONS_MONTHS, maturity_cutoff
from axon.ingest import IN_RESIDENCE_STATUSES

LEFT_HOUSE_STATUSES = ["discharged", "aftercare", "alumni"]
OUTCOME_CATEGORIES = ["engaged_in_recovery", "relapse_reported", "lost_to_follow_up", "unknown", "not_recorded"]
NO_OUTCOME_CATEGORIES = ["lost_to_follow_up", "unknown", "not_recorded"]


@dataclass
class Model:
    residents: pd.DataFrame
    followups: pd.DataFrame
    nightly_census: pd.DataFrame
    capacity: int
    as_of: date
    estimated_stay_days: float  # used to estimate missing discharge dates (occupancy only)


def build_model(raw: pd.DataFrame, as_of: date = AS_OF) -> Model:
    capacity = int(raw["bed_capacity"].iloc[0])
    residents = _residents(raw, as_of)
    followups = _followups(residents, as_of)
    census = _nightly_census(residents, capacity, as_of)
    return Model(
        residents=residents,
        followups=followups,
        nightly_census=census,
        capacity=capacity,
        as_of=as_of,
        estimated_stay_days=float(residents.attrs["estimated_stay_days"]),
    )


def followup_due_dates(discharge_date: pd.Series, months: int) -> pd.Series:
    """Follow-ups are timed from discharge (consistent with every record in the file)."""
    return discharge_date + pd.DateOffset(months=months)


def _days(later: pd.Series, earlier: pd.Series) -> pd.Series:
    return (later - earlier).dt.days.astype("Float64")


def _residents(raw: pd.DataFrame, as_of: date) -> pd.DataFrame:
    ts_as_of = pd.Timestamp(as_of)
    r = raw.drop(columns=["staff_note"]).copy()

    r["admitted"] = r["admission_date"].notna() & (r["admission_date"] <= ts_as_of)
    # D-07: someone admitted without an intake date still passed intake.
    r["reached_intake"] = r["intake_date"].notna() | r["admitted"]
    r["in_residence"] = r["current_status"].isin(IN_RESIDENCE_STATUSES)
    r["left_house"] = r["current_status"].isin(LEFT_HOUSE_STATUSES)

    reason = r["discharge_reason"].astype("object")
    r["discharge_reason"] = np.where(r["left_house"] & reason.isna(), "not_recorded", reason)
    r["discharge_reason"] = r["discharge_reason"].where(r["left_house"], None)
    # Completion follows the discharge reason. When the reason is blank, a graduate
    # status (aftercare, alumni) is only reachable by completing, so it decides.
    graduate_status = r["current_status"].isin(["aftercare", "alumni"])
    completed = (r["discharge_reason"] == "completed") | ((r["discharge_reason"] == "not_recorded") & graduate_status)
    r["completion_group"] = pd.Series(
        np.select([r["left_house"] & completed, r["left_house"]], ["completed", "early_leaver"], default=""),
        index=r.index,
    ).replace({"": None})

    # Stage timings. Pairs with a negative gap are data errors and are left out (D-07).
    ref_to_intake = _days(r["intake_date"], r["referral_date"])
    intake_to_adm = _days(r["admission_date"], r["intake_date"])
    r["days_referral_to_intake"] = ref_to_intake.where(ref_to_intake >= 0)
    r["days_intake_to_admission"] = intake_to_adm.where(intake_to_adm >= 0)
    r["days_referral_to_admission"] = _days(r["admission_date"], r["referral_date"])

    # Length of stay uses recorded discharge dates only. Estimates are for occupancy.
    r["los_days"] = _days(r["discharge_date"], r["admission_date"]).where(r["left_house"])
    r["days_in_house_so_far"] = _days(pd.Series(ts_as_of, index=r.index), r["admission_date"]).where(r["in_residence"])

    # D-06: estimate missing discharge dates as admission + median early-leaver stay.
    early = r["completion_group"].eq("early_leaver") & r["los_days"].notna()
    estimated_stay = float(r.loc[early, "los_days"].median()) if early.any() else 0.0
    needs_estimate = r["left_house"] & r["discharge_date"].isna() & r["admission_date"].notna()
    r["discharge_date_estimated"] = needs_estimate
    r["occupancy_end_date"] = r["discharge_date"]
    r.loc[needs_estimate, "occupancy_end_date"] = r.loc[needs_estimate, "admission_date"] + pd.to_timedelta(
        round(estimated_stay), unit="D"
    )

    r["referral_fy"] = r["referral_date"].dt.year
    r["admission_fy"] = r["admission_date"].dt.year.astype("Int64")
    r["discharge_fy"] = r["discharge_date"].dt.year.astype("Int64")
    r["matured"] = r["referral_date"] <= pd.Timestamp(maturity_cutoff(as_of))
    r["stage"] = np.select([r["admitted"], r["reached_intake"]], ["admitted", "intake"], default="referred")

    r.attrs["estimated_stay_days"] = estimated_stay
    return r.reset_index(drop=True)


def _followups(residents: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """One row per (resident who left the house, horizon).

    A follow-up is due when discharge date + horizon is on or before the extract date.
    If the discharge date is missing but an outcome was recorded, the record itself
    says it was due, so it is counted (D-07).
    """
    ts_as_of = pd.Timestamp(as_of)
    left = residents[residents["left_house"]]
    rows = []
    for months in FOLLOWUP_HORIZONS_MONTHS:
        recorded = left[f"followup_{months}m"]
        due_date = followup_due_dates(left["discharge_date"], months)
        has_outcome = recorded.notna() & (recorded != "not_yet_due")
        is_due = (due_date <= ts_as_of) | (left["discharge_date"].isna() & has_outcome)

        outcome = recorded.where(has_outcome, "not_recorded")
        outcome = outcome.where(is_due, "not_yet_due")
        rows.append(
            pd.DataFrame(
                {
                    "resident_id": left["resident_id"],
                    "horizon_months": months,
                    "discharge_date": left["discharge_date"],
                    "due_date": due_date,
                    "is_due": is_due,
                    "outcome": outcome,
                    "recorded_value": recorded,
                    "completion_group": left["completion_group"],
                    "discharge_reason": left["discharge_reason"],
                    "discharge_fy": left["discharge_fy"],
                    "fee_waived": left["fee_waived"],
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def _nightly_census(residents: pd.DataFrame, capacity: int, as_of: date) -> pd.DataFrame:
    """Midnight count: a resident fills a bed every night from admission up to, not including, discharge.

    Nights are observed up to the night before the extract date.
    """
    adm = residents[residents["admitted"]]
    if adm.empty:
        return pd.DataFrame({"night": pd.to_datetime([]), "residents": [], "residents_estimated": [], "capacity": []})
    first_night = adm["admission_date"].min()
    nights = pd.date_range(first_night, pd.Timestamp(as_of) - pd.Timedelta(days=1), freq="D")
    end = adm["occupancy_end_date"].fillna(pd.Timestamp(as_of))

    starts = adm["admission_date"].to_numpy()
    ends = end.to_numpy()
    estimated = adm["discharge_date_estimated"].to_numpy(dtype=bool)
    night_values = nights.to_numpy()[:, None]
    occupied = (night_values >= starts) & (night_values < ends)

    return pd.DataFrame(
        {
            "night": nights,
            "residents": occupied.sum(axis=1),
            "residents_estimated": occupied[:, estimated].sum(axis=1),
            "capacity": capacity,
        }
    )
