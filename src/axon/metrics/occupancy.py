"""Monthly occupancy from the nightly census: bed-nights / (beds x nights)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from axon.config import FiscalYear


@dataclass
class OccupancyResult:
    monthly: pd.DataFrame
    bed_nights: int
    capacity_nights: int
    estimated_bed_nights: int

    @property
    def rate(self) -> float | None:
        return None if self.capacity_nights == 0 else self.bed_nights / self.capacity_nights


def monthly_occupancy(census: pd.DataFrame, fy: FiscalYear | None = None) -> OccupancyResult:
    c = census.copy()
    if fy is not None:
        c = c[(c["night"] >= pd.Timestamp(fy.start)) & (c["night"] <= pd.Timestamp(fy.end))]
    c["month"] = c["night"].dt.to_period("M").dt.to_timestamp()
    m = (
        c.groupby("month")
        .agg(
            nights=("night", "size"),
            bed_nights=("residents", "sum"),
            capacity_nights=("capacity", "sum"),
            avg_residents=("residents", "mean"),
            peak_residents=("residents", "max"),
            estimated_bed_nights=("residents_estimated", "sum"),
            beds=("capacity", "max"),
        )
        .reset_index()
    )
    m["occupancy_rate"] = m["bed_nights"] / m["capacity_nights"]
    m["partial_month"] = m["nights"] < m["month"].dt.days_in_month
    return OccupancyResult(
        monthly=m,
        bed_nights=int(c["residents"].sum()),
        capacity_nights=int(c["capacity"].sum()),
        estimated_bed_nights=int(c["residents_estimated"].sum()),
    )
