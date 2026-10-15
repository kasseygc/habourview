"""Small, explicit statistics. Quantiles use linear interpolation, the same as DuckDB's quantile_cont."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Summary:
    n: int
    median: float | None
    p90: float | None


def summarize(values: pd.Series) -> Summary:
    v = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if v.size == 0:
        return Summary(0, None, None)
    return Summary(int(v.size), float(np.quantile(v, 0.5)), float(np.quantile(v, 0.9)))


def kaplan_meier(durations: pd.Series, observed: pd.Series) -> pd.DataFrame:
    """Kaplan-Meier survival curve.

    ``durations``: days from admission to discharge, or to the extract date if still in the house.
    ``observed``: True if the person has left (an event), False if still in the house (censored).
    At tied times, events are counted before censoring, which is the usual convention.
    """
    d = pd.DataFrame({"t": pd.to_numeric(durations), "e": observed.astype(bool)}).dropna()
    if d.empty:
        return pd.DataFrame(columns=["days", "at_risk", "left", "still_in_house", "share_still_in_house"])
    grouped = d.groupby("t")["e"].agg(left="sum", total="count").reset_index().sort_values("t")
    grouped["censored"] = grouped["total"] - grouped["left"]
    at_risk = len(d) - grouped["total"].cumsum().shift(fill_value=0)
    survival = (1 - grouped["left"] / at_risk).cumprod()
    return pd.DataFrame(
        {
            "days": grouped["t"].to_numpy(),
            "at_risk": at_risk.to_numpy(),
            "left": grouped["left"].to_numpy(),
            "still_in_house": grouped["censored"].to_numpy(),
            "share_still_in_house": survival.to_numpy(),
        }
    )


def km_median(curve: pd.DataFrame) -> float | None:
    """First time the estimated share still in the house falls to 50% or below; None if never."""
    reached = curve[curve["share_still_in_house"] <= 0.5]
    return None if reached.empty else float(reached["days"].iloc[0])


def rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator
