"""Seeded generator for fictional houses with the same columns and the same kinds of mess.

Used for the second tenant (tenant-isolation tests and demo) and for data-quality tests:
every injected problem is listed in a manifest, so tests can check the checks.
All names and phone numbers are invented; phone numbers use the 555 fictional range.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from axon.config import AS_OF
from axon.ingest import EXPECTED_COLUMNS

FEES = [0.0, 500.0, 750.0, 1000.0, 1250.0, 1500.0]
EARLY_REASONS = ["self_discharge", "administrative", "transfer", "other"]
EARLY_REASON_P = [0.6, 0.18, 0.14, 0.08]
FICTIONAL_CONTACTS = [
    ("aunt", "Marisol"), ("grandmother", "Edna"), ("brother", "Theo"), ("youth worker", "D. Okafor"),
    ("mom", "Renata"), ("caseworker", "P. Lindqvist"),
]

NOTES = {
    "not_admitted_no_intake": ["Unable to reach youth or guardian.", "Guardian declined - prefers day program.",
                               "pending - intake not booked yet", "No-show for intake appt."],
    "not_admitted_intake": ["Waitlisted. Will call when bed opens.", "Not appropriate for level of care.",
                            "Did not show on admission day", "Assessed - referred to detox first."],
    "in_residence": ["Settling in, attending school program.", "Good engagement in groups this wk.",
                     "Incident: argument w/ peer - resolved with staff.", "Low mood, check-in booked w/ counsellor."],
    "completed": ["Graduated. Attends alumni group.", "Completed program, living with family.",
                  "aftercare check-in by phone - doing well"],
    "early": ["Left program against advice.", "Transferred to a higher level of care.",
              "Discharged for repeated rule violations.", "Moved out of region with family."],
}


@dataclass
class Generated:
    frame: pd.DataFrame
    manifest: dict[str, list[str]] = field(default_factory=dict)


def generate(
    prefix: str = "GT",
    n: int = 150,
    capacity: int = 16,
    seed: int = 7,
    start: date = date(2024, 7, 1),
    end: date = date(2025, 12, 31),
    as_of: date = AS_OF,
) -> Generated:
    rng = np.random.default_rng(seed)
    span = (end - start).days
    referral_days = np.sort(rng.integers(0, span + 1, size=n))
    stays: list[tuple[date, date]] = []  # (admission, discharge or as_of) for bed tracking
    rows = []

    def beds_free(start: date, end: date) -> bool:
        day = start
        while day < max(end, start + timedelta(days=1)):
            if sum(1 for a, d in stays if a <= day < d) >= capacity:
                return False
            day += timedelta(days=1)
        return True

    for i, offset in enumerate(referral_days, start=1):
        rid = f"{prefix}-{i:04d}"
        referral = start + timedelta(days=int(offset))
        row = dict.fromkeys(EXPECTED_COLUMNS)
        row.update(resident_id=rid, referral_date=referral, current_status="not_admitted", bed_capacity=capacity)

        intake = referral + timedelta(days=1 + int(rng.gamma(2.0, 4.0)))
        if rng.random() > 0.72 or intake > as_of:
            row["staff_note"] = str(rng.choice(NOTES["not_admitted_no_intake"]))
            rows.append(row)
            continue
        row["intake_date"] = intake
        fee = float(rng.choice(FEES))
        row["entrance_fee"], row["fee_waived"] = fee, fee == 0.0

        completes = rng.random() < 0.5
        if completes:
            los = int(np.clip(rng.normal(140, 35), 70, 260))
        else:
            los = int(np.clip(rng.gamma(2.0, 25.0), 3, 220))

        # Wait for a bed that stays free for the whole stay, not just the first night.
        admission = intake + timedelta(days=1 + int(rng.gamma(2.0, 5.0)))
        waited = 0
        while not beds_free(admission, min(admission + timedelta(days=los), as_of)) and waited < 60:
            admission += timedelta(days=1)
            waited += 1
        if rng.random() > 0.72 or waited >= 60 or admission > as_of:
            row["staff_note"] = str(rng.choice(NOTES["not_admitted_intake"]))
            rows.append(row)
            continue
        row["admission_date"] = admission
        discharge = admission + timedelta(days=los)

        if discharge > as_of:
            days_in = (as_of - admission).days
            row["current_status"] = "phase_1" if days_in < 45 else "phase_2" if days_in < 100 else "phase_3"
            row["staff_note"] = str(rng.choice(NOTES["in_residence"]))
            stays.append((admission, as_of))
            rows.append(row)
            continue

        stays.append((admission, discharge))
        row["discharge_date"] = discharge
        if completes:
            row["discharge_reason"] = "completed"
            row["current_status"] = "aftercare" if (as_of - discharge).days < 180 else "alumni"
            row["staff_note"] = str(rng.choice(NOTES["completed"]))
            p = [0.55, 0.12, 0.25, 0.08]
        else:
            row["discharge_reason"] = str(rng.choice(EARLY_REASONS, p=EARLY_REASON_P))
            row["current_status"] = "discharged"
            row["staff_note"] = str(rng.choice(NOTES["early"]))
            p = [0.2, 0.3, 0.4, 0.1]
        for months in (6, 12):
            due = pd.Timestamp(discharge) + pd.DateOffset(months=months) <= pd.Timestamp(as_of)
            row[f"followup_{months}m"] = (
                str(rng.choice(["engaged_in_recovery", "relapse_reported", "lost_to_follow_up", "unknown"], p=p))
                if due else "not_yet_due"
            )
        rows.append(row)

    frame = pd.DataFrame(rows, columns=EXPECTED_COLUMNS)
    manifest = _inject_problems(frame, rng, as_of)
    return Generated(frame=frame, manifest=manifest)


def _inject_problems(df: pd.DataFrame, rng: np.random.Generator, as_of: date) -> dict[str, list[str]]:
    """Plant the same kinds of problems the real file has, and record exactly where."""
    manifest: dict[str, list[str]] = {}
    used: set[int] = set()

    def pick(mask: pd.Series, k: int) -> list[int]:
        pool = [i for i in df.index[mask] if i not in used]
        chosen = [int(i) for i in rng.choice(pool, size=min(k, len(pool)), replace=False)] if pool else []
        used.update(chosen)
        return chosen

    def record(rule: str, idx: list[int]) -> None:
        manifest[rule] = sorted(df.loc[idx, "resident_id"].tolist())

    admitted = df["admission_date"].notna()
    left = df["current_status"].isin(["discharged", "aftercare", "alumni"])
    early = df["current_status"] == "discharged"

    idx = pick(admitted & df["intake_date"].notna(), 3)
    df.loc[idx, "intake_date"] = None
    record("Admitted without an intake date", idx)

    idx = pick(df["intake_date"].notna() & ~admitted, 2)
    for i in idx:
        df.at[i, "intake_date"] = df.at[i, "referral_date"] - timedelta(days=int(rng.integers(2, 6)))
    record("Intake before referral", idx)

    idx = pick(early & (df["followup_6m"] == "not_yet_due"), 2)
    df.loc[idx, "discharge_date"] = None
    record("Left the house but no discharge date", idx)

    idx = pick(left & df["discharge_date"].notna(), 2)
    df.loc[idx, "discharge_reason"] = None
    record("No discharge reason", idx)

    due6 = left & df["followup_6m"].notna() & (df["followup_6m"] != "not_yet_due")
    idx = pick(due6, 2)
    df.loc[idx, "followup_6m"] = None
    record("6-month follow-up due but blank", idx)

    idx = pick(df["fee_waived"].eq(True), 1)
    df.loc[idx, "entrance_fee"] = 750.0
    record("Fee marked waived but an amount is recorded", idx)

    # PHI-like notes (fictional) - the redaction tests look for these.
    idx = pick(admitted, 3)
    for i, (relation, name) in zip(idx, rng.permutation(FICTIONAL_CONTACTS)[:3]):
        phone = f"416-555-{int(rng.integers(100, 200)):04d}"
        df.at[i, "staff_note"] = f"{str(relation).capitalize()} {name} called, asked for call back {phone}."
    record("PHI-like note", idx)

    # Cosmetic mess: stray whitespace, shouting, placeholders.
    for i in rng.choice(df.index, size=4, replace=False):
        df.at[i, "staff_note"] = f"  {df.at[i, 'staff_note']} "
    for i in rng.choice(df.index, size=3, replace=False):
        df.at[i, "staff_note"] = str(df.at[i, "staff_note"]).upper()
    for i in rng.choice(df.index, size=3, replace=False):
        df.at[i, "staff_note"] = str(rng.choice(["N/A", "-", "see paper file", None]))
    return manifest


def to_csv_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Format like the source file: ISO dates, '750.0' fees, 'True'/'False', blanks for nulls."""
    out = df.copy()
    for col in ["referral_date", "intake_date", "admission_date", "discharge_date"]:
        out[col] = out[col].map(lambda d: "" if d is None or pd.isna(d) else pd.Timestamp(d).strftime("%Y-%m-%d"))
    out["entrance_fee"] = out["entrance_fee"].map(lambda v: "" if v is None or pd.isna(v) else f"{float(v):.1f}")
    out["fee_waived"] = out["fee_waived"].map(lambda v: "" if v is None or pd.isna(v) else str(bool(v)))
    return out.fillna("")
