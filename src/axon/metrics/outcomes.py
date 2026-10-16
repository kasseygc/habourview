"""Follow-up outcomes for funders.

Denominator: every admitted resident who has left the house and whose follow-up date
has passed, including early leavers. Nobody is dropped for being unreachable.
"Engaged among those reached" is never computed: it is survivorship bias.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from axon.model import NO_OUTCOME_CATEGORIES, OUTCOME_CATEGORIES

OUTCOME_LABELS = {
    "engaged_in_recovery": "Engaged in recovery",
    "relapse_reported": "Relapse reported",
    "lost_to_follow_up": "Lost to follow-up",
    "unknown": "Unknown",
    "not_recorded": "Due but not recorded",
}


@dataclass
class OutcomeResult:
    horizon_months: int
    due_n: int
    not_yet_due_n: int
    counts: dict[str, int]  # every category, including zeros
    by_group: pd.DataFrame  # completion_group x outcome counts
    first_discharge: pd.Timestamp | None
    last_discharge: pd.Timestamp | None

    @property
    def engaged(self) -> int:
        return self.counts["engaged_in_recovery"]

    @property
    def relapse(self) -> int:
        return self.counts["relapse_reported"]

    @property
    def no_outcome(self) -> int:
        return sum(self.counts[c] for c in NO_OUTCOME_CATEGORIES)

    def share(self, n: int) -> float | None:
        return None if self.due_n == 0 else n / self.due_n

    @property
    def engaged_worst_case(self) -> float | None:
        """Everyone without an outcome assumed not engaged. Equals the confirmed rate."""
        return self.share(self.engaged)

    @property
    def engaged_best_case(self) -> float | None:
        """Everyone without an outcome assumed engaged."""
        return self.share(self.engaged + self.no_outcome)


def outcomes(followups: pd.DataFrame, horizon_months: int) -> OutcomeResult:
    f = followups[followups["horizon_months"] == horizon_months]
    due = f[f["is_due"]]
    counts = {c: int((due["outcome"] == c).sum()) for c in OUTCOME_CATEGORIES}
    by_group = (
        due.groupby(["completion_group", "outcome"]).size().unstack(fill_value=0).reindex(columns=OUTCOME_CATEGORIES, fill_value=0)
    )
    by_group["due"] = by_group.sum(axis=1)
    discharges = due["due_date"].dropna() - pd.DateOffset(months=horizon_months)
    return OutcomeResult(
        horizon_months=horizon_months,
        due_n=len(due),
        not_yet_due_n=int((~f["is_due"]).sum()),
        counts=counts,
        by_group=by_group,
        first_discharge=None if discharges.empty else discharges.min(),
        last_discharge=None if discharges.empty else discharges.max(),
    )
