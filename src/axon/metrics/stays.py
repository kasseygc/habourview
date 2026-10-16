"""Length of stay for one fiscal-year admission cohort.

Finished stays and ongoing stays are reported separately. A Kaplan-Meier estimate
combines them, treating ongoing stays as censored at the extract date.
Stays with no recorded discharge date are excluded (their length is unknown).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from axon.config import FiscalYear
from axon.stats import Summary, kaplan_meier, km_median, summarize


@dataclass
class StaysResult:
    fy: FiscalYear
    admitted_n: int
    finished: pd.DataFrame  # by group: n, median, p90
    finished_all: Summary
    ongoing: Summary
    ongoing_max: float | None
    missing_discharge_date: int
    km_curve: pd.DataFrame
    km_median_days: float | None


def stays(residents: pd.DataFrame, fy: FiscalYear) -> StaysResult:
    cohort = residents[residents["admitted"] & (residents["admission_fy"] == fy.year)]
    finished = cohort[cohort["left_house"] & cohort["los_days"].notna()]
    ongoing = cohort[cohort["in_residence"]]
    missing = cohort[cohort["left_house"] & cohort["los_days"].isna()]

    rows = []
    for label, part in [
        ("Completed the program", finished[finished["completion_group"] == "completed"]),
        ("Left early (all reasons)", finished[finished["completion_group"] == "early_leaver"]),
    ]:
        s = summarize(part["los_days"])
        rows.append({"group": label, "n": s.n, "median_days": s.median, "p90_days": s.p90})
    for reason, part in finished[finished["completion_group"] == "early_leaver"].groupby("discharge_reason"):
        s = summarize(part["los_days"])
        rows.append({"group": f"  {reason.replace('_', ' ')}", "n": s.n, "median_days": s.median, "p90_days": s.p90})

    durations = pd.concat([finished["los_days"], ongoing["days_in_house_so_far"]])
    observed = pd.concat([pd.Series(True, index=finished.index), pd.Series(False, index=ongoing.index)])
    curve = kaplan_meier(durations, observed)

    return StaysResult(
        fy=fy,
        admitted_n=len(cohort),
        finished=pd.DataFrame(rows),
        finished_all=summarize(finished["los_days"]),
        ongoing=summarize(ongoing["days_in_house_so_far"]),
        ongoing_max=None if ongoing.empty else float(ongoing["days_in_house_so_far"].max()),
        missing_discharge_date=len(missing),
        km_curve=curve,
        km_median_days=km_median(curve),
    )
