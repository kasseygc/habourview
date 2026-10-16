"""Plain-language answers, written by templates from the query result.

The LLM never writes the answer text, so every number a user reads came from the executed query.
"""

from __future__ import annotations

import pandas as pd

from axon.agent.registry import METRICS
from axon.agent.spec import QuerySpec
from axon.config import AS_OF
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
        return _residents_now(spec, df)
    if spec.metric == "entrance_fees":
        return _fees(spec, df)
    if spec.metric == "notes_mentions":
        return _notes(spec, df)
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


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _fees(spec: QuerySpec, df: pd.DataFrame) -> str:
    status = next((f for f in spec.filters if f.field == "fee_status"), None)
    who = {"paid": "people charged", "waived": "people whose fee was waived"}.get(
        str(status.values[0]) if status else "", "people with a fee record (waived fees counted as $0)")
    n, total = int(df["n"].sum()), float(df["total_fee"].sum())
    text = f"Average entrance fee {_money(total / n)} for {n} {who}, {window_phrase(spec)}; total {_money(total)}."
    if not spec.group_by:
        return text + f" Median {_money(df['median_fee'].iloc[0])}."
    col = spec.group_by[0]
    groups = [(("no intake date" if pd.isna(k) else k), a, c) for k, a, c in zip(df[col], df["avg_fee"], df["n"]) if c]
    return text + " " + "; ".join(f"{k}: {_money(a)} (n {int(c)})" for k, a, c in groups) + "."


def _notes(spec: QuerySpec, df: pd.DataFrame) -> str:
    """What notes say, as counts and the notes' own redacted phrases. Never who."""
    topics = next((f for f in spec.filters if f.field == "note_topic"), None)
    about = " or ".join(label(str(v)) for v in topics.values) if topics and topics.op == "in" else "these topics"
    by = next((g for g in spec.group_by if g in ("note_topic", "note_field")), None)
    if by:
        parts = df.groupby(by)["people"].sum().sort_values(ascending=False)
        text = "Staff notes mention: " + "; ".join(f"{label(str(k))} {int(v)}" for k, v in parts.items()) + " (people)."
    else:
        text = f"Staff notes mention {about} for {int(df['people'].sum())} people"
        if "current_status" in spec.group_by:
            text += " (" + ", ".join(f"{STATUS_LABELS.get(s, s)} {int(n)}" for s, n in zip(df["current_status"], df["people"])) + ")"
        text += "."
    phrases = sorted({p for cell in df["phrases"].dropna() for p in str(cell).split(" | ") if p})
    if phrases:
        shown = "; ".join(f"“{p}”" for p in phrases[:6])
        text += f" In the notes' words, redacted: {shown}" + (f" and {len(phrases) - 6} more." if len(phrases) > 6 else ".")
    if df["unconfirmed"].any():
        text += " Not yet confirmed by staff."
    return text


def _residents_now(spec: QuerySpec, df: pd.DataFrame) -> str:
    total = int(df["n"].sum())
    statuses = next((f for f in spec.filters if f.field == "current_status"), None)
    if "current_status" in df.columns:
        parts = ", ".join(f"{STATUS_LABELS.get(s, s)} {n}" for s, n in zip(df["current_status"], df["n"]))
        return f"On {AS_OF:%d %b %Y}: {total} people ({parts})."
    if statuses is None:
        return (f"{total} people have been admitted since the data starts (July 2024), counting every current "
                f"status on {AS_OF:%d %b %Y}: in the house, aftercare, alumni and people who left.")
    which = ", ".join(STATUS_LABELS.get(str(v), str(v)) for v in statuses.values)
    return f"On {AS_OF:%d %b %Y}: {total} people " + ("not " if statuses.op == "not_in" else "") + f"in {which}."


def _occupancy(spec: QuerySpec, df: pd.DataFrame) -> str:
    nights = df["nights"].sum()
    beds = int(df["beds"].max())
    if nights == 1:
        n = int(df["peak_residents"].iloc[0])
        night = spec.time_window.start
        return f"On the night of {night:%d %b %Y}, {n} of {beds} beds were filled ({n / beds:.0%})."
    overall = (df["occupancy_rate"] * df["beds"] * df["nights"]).sum() / (df["beds"] * df["nights"]).sum()
    avg = (df["avg_residents"] * df["nights"]).sum() / nights
    text = f"Beds were {overall:.0%} full on average {window_phrase(spec)} ({avg:.1f} of {beds} beds a night)."
    if not spec.group_by:
        return text + f" Highest single night: {int(df['peak_residents'].max())} of {beds}."
    col = spec.group_by[0]
    hi = df.loc[df["occupancy_rate"].idxmax()]
    lo = df.loc[df["occupancy_rate"].idxmin()]
    return (
        f"{text} Fullest {col.replace('_', ' ')}: {hi[col]} ({hi['occupancy_rate']:.0%}); "
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
    chosen = next((f for f in spec.filters if f.field == "outcome"), None)
    if chosen is not None and "outcome" not in spec.group_by:
        which = " or ".join(OUTCOME_LABELS[str(v)].lower() for v in chosen.values)
        n = int(df["n"].sum())
        if chosen.op == "not_in":
            return f"{n} people whose {h} follow-up was due had an outcome other than {which}."
        return f"{n} people whose {h} follow-up was due: {which}."
    if "outcome" not in df.columns:
        return f"{int(df['n'].sum())} people had a {h} follow-up due."
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
    count_cols = [c for c in ("n", "due", "people") if c in df.columns]
    if any(is_small(int(v)) for c in count_cols for v in df[c]):
        return "Some groups have fewer than 5 people. Read those with care, and don't share them outside the house."
    return None
