"""Read a house's resident CSV into a typed DataFrame. No business rules here."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATE_COLUMNS = ["referral_date", "intake_date", "admission_date", "discharge_date"]

STATUSES = ["phase_1", "phase_2", "phase_3", "aftercare", "alumni", "discharged", "not_admitted"]
IN_RESIDENCE_STATUSES = ["phase_1", "phase_2", "phase_3"]
DISCHARGE_REASONS = ["completed", "self_discharge", "administrative", "transfer", "other"]
FOLLOWUP_VALUES = ["engaged_in_recovery", "relapse_reported", "unknown", "lost_to_follow_up", "not_yet_due"]

EXPECTED_COLUMNS = [
    "resident_id",
    "referral_date",
    "intake_date",
    "admission_date",
    "current_status",
    "discharge_date",
    "discharge_reason",
    "entrance_fee",
    "fee_waived",
    "followup_6m",
    "followup_12m",
    "staff_note",
    "bed_capacity",
]


class SchemaError(ValueError):
    pass


def read_residents(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = set(EXPECTED_COLUMNS) - set(raw.columns)
    if missing:
        raise SchemaError(f"{path.name} is missing columns: {sorted(missing)}")

    df = raw[EXPECTED_COLUMNS].copy()
    df = df.apply(lambda s: s.str.strip()).replace({"": None})

    for col in DATE_COLUMNS:
        df[col] = pd.to_datetime(df[col], format="%Y-%m-%d", errors="raise")
    df["entrance_fee"] = pd.to_numeric(df["entrance_fee"])
    df["fee_waived"] = df["fee_waived"].map({"True": True, "False": False}).astype("boolean")
    df["bed_capacity"] = pd.to_numeric(df["bed_capacity"]).astype("Int64")
    # Free text is kept as-is (only trimmed). It never reaches the analytics warehouse.
    df["staff_note"] = raw["staff_note"].replace({"": None})

    _check_enum(df, "current_status", STATUSES)
    _check_enum(df, "discharge_reason", DISCHARGE_REASONS)
    _check_enum(df, "followup_6m", FOLLOWUP_VALUES)
    _check_enum(df, "followup_12m", FOLLOWUP_VALUES)
    if df["resident_id"].duplicated().any():
        raise SchemaError("Duplicate resident_id values")
    if df["bed_capacity"].nunique() != 1:
        raise SchemaError("bed_capacity should be constant within a house")
    return df


def _check_enum(df: pd.DataFrame, col: str, allowed: list[str]) -> None:
    bad = set(df[col].dropna()) - set(allowed)
    if bad:
        raise SchemaError(f"Unexpected values in {col}: {sorted(bad)}")
