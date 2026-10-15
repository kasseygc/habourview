"""Referral -> intake -> admission for one fiscal-year referral cohort (D-02, D-03).

Conversion rates and stage timings use only referrals that had MATURITY_DAYS to progress
before the extract date. Later referrals are reported separately as "too recent to judge".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from axon.config import AS_OF, FiscalYear, maturity_cutoff
from axon.stats import Summary, rate, summarize


@dataclass
class StageRow:
    stage: str
    n: int
    of: int  # the denominator for the conversion from the previous stage

    @property
    def rate(self) -> float | None:
        return rate(self.n, self.of)


@dataclass
class FunnelResult:
    fy: FiscalYear
    cutoff: date
    cohort_n: int
    matured_n: int
    stages: list[StageRow]
    overall: StageRow  # referral -> admission
    timings: dict[str, Summary]
    timing_exclusions: dict[str, int]
    recent: pd.DataFrame  # too-recent referrals: stage, n, median days since referral


def funnel(residents: pd.DataFrame, fy: FiscalYear, as_of: date = AS_OF) -> FunnelResult:
    cohort = residents[residents["referral_fy"] == fy.year]
    matured = cohort[cohort["matured"]]
    referred = len(matured)
    reached_intake = int(matured["reached_intake"].sum())
    admitted = int(matured["admitted"].sum())

    with_intake = matured[matured["intake_date"].notna()]
    timings = {
        "Referral to intake": summarize(matured["days_referral_to_intake"]),
        "Intake to admission": summarize(matured["days_intake_to_admission"]),
        "Referral to admission": summarize(matured["days_referral_to_admission"]),
    }
    timing_exclusions = {
        "Referral to intake": int((with_intake["days_referral_to_intake"].isna()).sum()),
        "Intake to admission": int((matured["admitted"] & matured["intake_date"].isna()).sum()),
    }

    recent = cohort[~cohort["matured"]].copy()
    recent["days_since_referral"] = (pd.Timestamp(as_of) - recent["referral_date"]).dt.days
    stage_order = {"referred": "Waiting for intake", "intake": "Intake done, not yet admitted", "admitted": "Admitted"}
    recent_summary = (
        recent.assign(stage_label=recent["stage"].map(stage_order))
        .groupby("stage_label", sort=False)
        .agg(n=("resident_id", "size"), median_days_since_referral=("days_since_referral", "median"))
        .reindex(list(stage_order.values()))
        .fillna({"n": 0})
        .astype({"n": int})
        .reset_index()
        .rename(columns={"stage_label": "stage"})
    )

    return FunnelResult(
        fy=fy,
        cutoff=maturity_cutoff(as_of),
        cohort_n=len(cohort),
        matured_n=referred,
        stages=[
            StageRow("Referred", referred, referred),
            StageRow("Reached intake", reached_intake, referred),
            StageRow("Admitted", admitted, reached_intake),
        ],
        overall=StageRow("Admitted", admitted, referred),
        timings=timings,
        timing_exclusions=timing_exclusions,
        recent=recent_summary,
    )
