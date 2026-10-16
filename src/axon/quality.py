"""Data-quality checks. Every issue names the resident, the rule and how metrics treat it."""

from __future__ import annotations

from datetime import date

import pandas as pd

from axon.config import AS_OF
from axon.ingest import DATE_COLUMNS, IN_RESIDENCE_STATUSES
from axon.model import LEFT_HOUSE_STATUSES, Model, followup_due_dates

ISSUE_COLUMNS = ["resident_id", "rule", "detail", "treatment"]


def check(raw: pd.DataFrame, model: Model, as_of: date = AS_OF) -> pd.DataFrame:
    ts = pd.Timestamp(as_of)
    issues: list[pd.DataFrame] = []

    def add(mask: pd.Series, rule: str, detail, treatment: str) -> None:
        hit = raw[mask.fillna(False)]
        if hit.empty:
            return
        details = hit.apply(detail, axis=1) if callable(detail) else detail
        issues.append(
            pd.DataFrame({"resident_id": hit["resident_id"], "rule": rule, "detail": details, "treatment": treatment})
        )

    left = raw["current_status"].isin(LEFT_HOUSE_STATUSES)
    admitted = raw["admission_date"].notna()

    add(
        admitted & raw["intake_date"].isna(),
        "Admitted without an intake date",
        lambda r: f"admitted {r.admission_date:%Y-%m-%d}",
        "Counted as having passed intake; left out of intake timings.",
    )
    add(
        raw["intake_date"] < raw["referral_date"],
        "Intake before referral",
        lambda r: f"referral {r.referral_date:%Y-%m-%d}, intake {r.intake_date:%Y-%m-%d}",
        "Left out of referral-to-intake timing.",
    )
    add(
        raw["admission_date"] < raw["intake_date"],
        "Admission before intake",
        lambda r: f"intake {r.intake_date:%Y-%m-%d}, admission {r.admission_date:%Y-%m-%d}",
        "Left out of intake-to-admission timing.",
    )
    add(
        raw["discharge_date"] < raw["admission_date"],
        "Discharge before admission",
        lambda r: f"admission {r.admission_date:%Y-%m-%d}, discharge {r.discharge_date:%Y-%m-%d}",
        "Left out of length of stay.",
    )
    add(
        left & raw["discharge_date"].isna(),
        "Left the house but no discharge date",
        lambda r: f"status {r.current_status}, admitted {r.admission_date:%Y-%m-%d}",
        f"Discharge estimated at admission + {model.estimated_stay_days:.0f} days (median early-leaver stay) "
        "for occupancy only; left out of length of stay.",
    )
    add(
        left & raw["discharge_reason"].isna(),
        "No discharge reason",
        lambda r: f"status {r.current_status}",
        "Reason reported as 'not recorded'. Completion follows status: aftercare or alumni count as completed, "
        "discharged as an early leaver.",
    )
    add(
        raw["current_status"].isin(["aftercare", "alumni"]) & raw["discharge_reason"].notna()
        & (raw["discharge_reason"] != "completed"),
        "Graduate status with a non-completion reason",
        lambda r: f"status {r.current_status}, reason {r.discharge_reason}",
        "Discharge reason is trusted for completion; status is shown as recorded.",
    )
    add(
        raw["current_status"].isin(IN_RESIDENCE_STATUSES) & raw["discharge_date"].notna(),
        "In residence but has a discharge date",
        lambda r: f"status {r.current_status}, discharge {r.discharge_date:%Y-%m-%d}",
        "Status is trusted: counted as in the house.",
    )
    add(
        (raw["current_status"] != "not_admitted") & ~admitted,
        "Admitted status without an admission date",
        lambda r: f"status {r.current_status}",
        "Left out of occupancy and length of stay.",
    )
    for col in DATE_COLUMNS:
        add(
            raw[col] > ts,
            "Date after the extract date",
            lambda r, c=col: f"{c} {r[c]:%Y-%m-%d}",
            "Treated as not yet happened.",
        )

    for months in (6, 12):
        col = f"followup_{months}m"
        due = followup_due_dates(raw["discharge_date"], months) <= ts
        add(
            left & due & raw[col].isna(),
            f"{months}-month follow-up due but blank",
            lambda r: f"discharged {r.discharge_date:%Y-%m-%d}",
            "Reported as 'not recorded' in the unreached group.",
        )
        add(
            left & due & (raw[col] == "not_yet_due"),
            f"{months}-month follow-up due but marked not yet due",
            lambda r: f"discharged {r.discharge_date:%Y-%m-%d}",
            "Reported as 'not recorded' in the unreached group.",
        )
        add(
            left & raw["discharge_date"].notna() & ~due & raw[col].notna() & (raw[col] != "not_yet_due"),
            f"{months}-month outcome recorded before it was due",
            lambda r, c=col: f"discharged {r.discharge_date:%Y-%m-%d}, recorded {r[c]}",
            "Not counted until the follow-up date has passed.",
        )
        add(
            left & raw["discharge_date"].isna() & raw[col].notna() & (raw[col] != "not_yet_due"),
            f"{months}-month outcome recorded without a discharge date",
            lambda r, c=col: f"recorded {r[c]}",
            "Counted as due, because an outcome was recorded.",
        )

    add(
        raw["fee_waived"].eq(True) & (raw["entrance_fee"] > 0),
        "Fee marked waived but an amount is recorded",
        lambda r: f"fee {r.entrance_fee:.0f}",
        "Not used in any metric.",
    )
    add(
        raw["fee_waived"].eq(False) & (raw["entrance_fee"] == 0),
        "Fee of 0 but not marked waived",
        "fee 0",
        "Not used in any metric.",
    )

    over = model.nightly_census[model.nightly_census["residents"] > model.capacity]
    if not over.empty:
        with_estimates = int((over["residents_estimated"] > 0).sum())
        cause = (
            "every one includes an estimated discharge date, so the estimate is likely too long"
            if with_estimates == len(over)
            else f"{with_estimates} include an estimated discharge date; the rest point to a date-entry error"
        )
        issues.append(
            pd.DataFrame(
                {
                    "resident_id": ["(house)"],
                    "rule": ["More residents than beds on some nights"],
                    "detail": [f"{len(over)} nights, peak {over['residents'].max()} of {model.capacity}; {cause}"],
                    "treatment": ["Shown as calculated, not capped."],
                }
            )
        )

    if not issues:
        return pd.DataFrame(columns=ISSUE_COLUMNS)
    return pd.concat(issues, ignore_index=True)[ISSUE_COLUMNS]
