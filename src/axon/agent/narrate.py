"""Plain-language answers, written by templates from the query result.

The LLM never writes the answer text, so every number a user reads came from the executed query.
"""

from __future__ import annotations

import pandas as pd

from axon.agent.registry import METRICS
from axon.agent.spec import QuerySpec
from axon.metrics.outcomes import OUTCOME_LABELS
from axon.notes.schema import label
from axon.suppress import is_small

STATUS_LABELS = {"phase_1": "phase 1", "phase_2": "phase 2", "phase_3": "phase 3", "aftercare": "aftercare",
                 "alumni": "alumni", "discharged": "left early"}
GROUP_LABELS = {"completed": "people who completed", "early_leaver": "people who left early"}


def pct(x: float | None) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:.0%}"


def window_phrase(spec: QuerySpec) -> str:
    tw = spec.time_window
    if tw.preset == "all":
        return "across all the data"
    if tw.preset == "custom":
        return f"from {tw.start:%d %b %Y} to {tw.end:%d %b %Y}"
    return f"in {tw.preset.upper().replace('FY', 'FY')}"


def narrate(spec: QuerySpec, df: pd.DataFrame) -> str:
    m = METRICS[spec.metric]
    if df.empty:
        return "No records match this question."
    if spec.metric == "occupancy":
        return _occupancy(spec, df)
    if spec.metric == "followup_engaged_rate":
        return _engaged(spec, df)
    if spec.metric == "followup_outcomes":
        return _outcomes(spec, df)
    if spec.metric == "referrals_by_note":
        total = int(df["n"].sum())
        text = f"{total} referrals were not admitted {window_phrase(spec)}."
        col = next((g for g in spec.group_by if g.startswith("note_")), None)
        if col:
            by = df.groupby(col)["n"].sum().sort_values(ascending=False)
            text += " The staff notes say: " + "; ".join(f"{label(k)} {v}" for k, v in by.items()) + "."
        return text
    if spec.metric == "residents_now":
        total = int(df["n"].sum())
        if "current_status" not in df.columns:
            return f"{total} people as of the extract date."
        parts = ", ".join(f"{STATUS_LABELS.get(s, s)} {n}" for s, n in zip(df["current_status"], df["n"]))
        return f"{total} people as of the extract date ({parts})."
    return _counts(spec, df, m.label.lower())


def _counts(spec: QuerySpec, df: pd.DataFrame, label: str) -> str:
    total = int(df["n"].sum())
    text = f"{total} {label} {window_phrase(spec)}."
    if spec.group_by and spec.group_by[0] in ("month", "quarter") and len(df) > 1:
        col = spec.group_by[0]
        by = df.groupby(col)["n"].sum()
        text += f" Lowest: {by.min()} ({by.idxmin()}); highest: {by.max()} ({by.idxmax()})."
    elif spec.group_by:
        col = spec.group_by[0]
        by = df.groupby(col)["n"].sum().sort_values(ascending=False)
        text += " " + "; ".join(f"{k.replace('_', ' ')}: {v} ({v / total:.0%})" for k, v in by.items()) + "."
    return text


def _occupancy(spec: QuerySpec, df: pd.DataFrame) -> str:
    nights = df["nights"].sum()
    overall = (df["occupancy_rate"] * df["beds"] * df["nights"]).sum() / (df["beds"] * df["nights"]).sum()
    avg = (df["avg_residents"] * df["nights"]).sum() / nights
    col = spec.group_by[0]
    hi = df.loc[df["occupancy_rate"].idxmax()]
    lo = df.loc[df["occupancy_rate"].idxmin()]
    beds = int(df["beds"].max())
    return (
        f"Beds were {overall:.0%} full on average {window_phrase(spec)} ({avg:.1f} of {beds} beds a night). "
        f"Fullest {col.replace('_', ' ')}: {hi[col]} ({hi['occupancy_rate']:.0%}); "
        f"emptiest: {lo[col]} ({lo['occupancy_rate']:.0%}). Highest single night: {int(df['peak_residents'].max())} of {beds}."
    )


def _horizon(spec: QuerySpec) -> str:
    h = next(f.values[0] for f in spec.filters if f.field == "horizon")
    return {"6m": "6-month", "12m": "12-month"}[h]


def _engaged_line(row: pd.Series, who: str) -> str:
    due, engaged, none_ = int(row["due"]), int(row["engaged"]), int(row["no_outcome"])
    worst, best = engaged / due, (engaged + none_) / due
    return (
        f"Of {due} {who}, {engaged} ({worst:.0%}) were confirmed engaged in recovery. "
        f"{none_} have no known outcome, so the true share is between {worst:.0%} (worst case: none of them engaged) "
        f"and {best:.0%} (best case: all of them)."
    )


def _engaged(spec: QuerySpec, df: pd.DataFrame) -> str:
    h = _horizon(spec)
    if not spec.group_by:
        return _engaged_line(df.iloc[0], f"people whose {h} follow-up was due")
    col = spec.group_by[0]
    return " ".join(_engaged_line(r, f"{GROUP_LABELS.get(r[col], r[col])} with a {h} follow-up due") for _, r in df.iterrows())


def _outcomes(spec: QuerySpec, df: pd.DataFrame) -> str:
    h = _horizon(spec)
    by = df.groupby("outcome")["n"].sum()
    due = int(by.sum())
    engaged = int(by.get("engaged_in_recovery", 0))
    relapse = int(by.get("relapse_reported", 0))
    none_ = due - engaged - relapse
    text = (
        f"{due} people had a {h} follow-up due. {engaged} ({engaged / due:.0%}) engaged in recovery, "
        f"{relapse} ({relapse / due:.0%}) relapse reported, and {none_} ({none_ / due:.0%}) no known outcome "
        f"({', '.join(f'{OUTCOME_LABELS[k].lower()} {int(by.get(k, 0))}' for k in ['lost_to_follow_up', 'unknown', 'not_recorded'])})."
    )
    return text


def small_cell_note(df: pd.DataFrame, spec: QuerySpec) -> str | None:
    count_cols = [c for c in ("n", "due") if c in df.columns]
    if any(is_small(int(v)) for c in count_cols for v in df[c]):
        return "Some groups have fewer than 5 people. Read those with care, and don't share them outside the house."
    return None
