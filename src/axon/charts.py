"""Altair (Vega-Lite) charts shared by the dashboard, the agent and the funder report.

Axon Health's palette (read from axonhealth.io), checked with the dataviz skill's validator on white:
- known outcomes in sage: dark #446a3f (completed, engaged), light #92b68c (left by choice, relapse);
- everything we don't know, or that isn't a completion, in one lavender-grey ordered ramp;
- red / amber / green are status colours and never appear as data series.
Light sage is 2.3:1 on white, so every chart that uses it carries counts in its legend or a table.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from axon.agent.registry import DIMENSIONS, METRICS
from axon.agent.spec import QuerySpec
from axon.metrics.outcomes import OUTCOME_LABELS

SAGE = "#446a3f"
SAGE_LIGHT = "#92b68c"
GREY_1, GREY_2, GREY_3 = "#54586b", "#7e7d91", "#a9a7b8"
MUTED = GREY_3        # reference lines
INK = "#21273f"
INK_2 = "#54586b"     # axis and label text
GRID = "#f0f0f3"
FONT = "Inter, system-ui, sans-serif"
TEAL, TEAL_LIGHT = SAGE, SAGE_LIGHT  # names used by older call sites
BLUE, ORANGE = SAGE, SAGE_LIGHT
OUTCOME_COLORS = {
    "Engaged in recovery": SAGE,
    "Relapse reported": SAGE_LIGHT,
    # Ordered grey ramp: tried and failed -> unknown -> never recorded.
    "Lost to follow-up": GREY_1,
    "Unknown": GREY_2,
    "Due but not recorded": GREY_3,
}
OUTCOME_ORDER = list(OUTCOME_COLORS)
GROUP_LABELS = {"completed": "Completed the program", "early_leaver": "Left early"}
EXIT_COLORS = {
    "completed": ("Completed", SAGE),
    "left_by_choice": ("Left by choice", SAGE_LIGHT),
    "discharged_by_house": ("Discharged by the house", GREY_1),
    "transferred": ("Transferred", GREY_2),
    "custody": ("Custody", GREY_3),
    "other_or_unknown": ("Other or unknown", GREY_3),
    "still_in_program": ("Still in the program", "#ffffff"),
}

BAR = {"cornerRadiusEnd": 4}
WIDTH = "container"


def _base(df: pd.DataFrame) -> alt.Chart:
    return alt.Chart(df).properties(width=WIDTH, height=260)


def _fit(chart):
    """Stretch to the container's width only. Plain 'fit' would squeeze the plot so axes and legend fit the height."""
    return (
        chart.properties(autosize=alt.AutoSizeParams(type="fit-x", contains="padding"), padding={"top": 8, "bottom": 8, "left": 4, "right": 12})
        .configure(background="transparent", font=FONT)
        .configure_axis(labelColor=INK_2, titleColor=INK_2, gridColor=GRID, domainColor="#d7d5e0", tickColor="#d7d5e0",
                        labelFontSize=12, titleFontSize=12, titleFontWeight=500, titlePadding=10, labelPadding=6)
        .configure_legend(labelColor=INK_2, labelFontSize=12, symbolSize=120, rowPadding=8, columnPadding=16, padding=10)
        .configure_view(stroke=None)
    )


def funnel_chart(stages: list) -> alt.Chart:
    df = pd.DataFrame(
        [{"stage": s.stage, "n": s.n, "label": f"{s.n}" + ("" if i == 0 else f"  ({s.n / s.of:.0%} of {s.of})")}
         for i, s in enumerate(stages)]
    )
    order = df["stage"].tolist()
    bars = _base(df).mark_bar(color=BLUE, **BAR).encode(
        y=alt.Y("stage:N", sort=order, title=None),
        x=alt.X("n:Q", title="People"),
        tooltip=[alt.Tooltip("stage:N", title="Stage"), alt.Tooltip("label:N", title="People")],
    )
    text = bars.mark_text(align="left", dx=6, color=INK_2).encode(text="label:N")
    return _fit((bars + text).properties(height=150))


def occupancy_chart(monthly: pd.DataFrame) -> alt.Chart:
    df = monthly.assign(
        month_label=monthly["month"].dt.strftime("%b %Y"),
        note=monthly["partial_month"].map({True: "partial month", False: ""}),
    )
    line = _base(df).mark_line(color=BLUE, strokeWidth=2, point=alt.OverlayMarkDef(size=60, filled=True, color=BLUE)).encode(
        x=alt.X("month:T", title=None,
                axis=alt.Axis(format="%b %y", tickCount={"interval": "month", "step": 1}, labelAngle=0, labelOverlap="greedy")),
        y=alt.Y("occupancy_rate:Q", title="Beds filled", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1.05])),
        tooltip=[
            alt.Tooltip("month_label:N", title="Month"),
            alt.Tooltip("occupancy_rate:Q", title="Occupancy", format=".1%"),
            alt.Tooltip("avg_residents:Q", title="Average residents a night", format=".1f"),
            alt.Tooltip("peak_residents:Q", title="Busiest night"),
            alt.Tooltip("beds:Q", title="Beds"),
            alt.Tooltip("note:N", title=" "),
        ],
    )
    full = alt.Chart(pd.DataFrame({"y": [1.0]})).mark_rule(color=MUTED, strokeDash=[4, 4]).encode(y="y:Q")
    return _fit(full + line)


def census_chart(census: pd.DataFrame) -> alt.Chart:
    """Residents in the house each night, against the number of beds."""
    df = census.assign(day=census["night"].dt.strftime("%a %d %b %Y"))
    beds = int(census["capacity"].max())
    line = _base(df).mark_line(color=TEAL, strokeWidth=1.75, interpolate="step-after").encode(
        x=alt.X("night:T", title=None, axis=alt.Axis(format="%b", tickCount={"interval": "month", "step": 1}, labelAngle=0)),
        y=alt.Y("residents:Q", title="Residents", scale=alt.Scale(domain=[0, beds + 2]), axis=alt.Axis(tickCount=4)),
        tooltip=[alt.Tooltip("day:N", title="Night"), alt.Tooltip("residents:Q", title="Residents"),
                 alt.Tooltip("capacity:Q", title="Beds")],
    )
    cap = alt.Chart(pd.DataFrame({"y": [beds], "label": [f"{beds} beds"]}))
    rule = cap.mark_rule(color=MUTED, strokeDash=[4, 4]).encode(y="y:Q")
    text = cap.mark_text(align="left", dx=4, dy=-7, color=INK_2, fontSize=11).encode(y="y:Q", x=alt.value(0), text="label:N")
    return _fit((rule + text + line).properties(height=255))


def flow_chart(residents: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> alt.Chart:
    """Admissions and discharges side by side, by month."""
    months = pd.period_range(start, end, freq="M")
    rows = []
    for label, col in (("Admissions", "admission_date"), ("Discharges", "discharge_date")):
        d = residents[col].dropna()
        d = d[(d >= start) & (d <= end + pd.Timedelta(days=1))]
        counts = d.dt.to_period("M").value_counts().reindex(months, fill_value=0)
        rows += [{"month": m.to_timestamp(), "kind": label, "n": int(n)} for m, n in counts.items()]
    df = pd.DataFrame(rows)
    df["month_label"] = df["month"].dt.strftime("%b %Y")
    return _fit(
        _base(df).mark_bar(**BAR).encode(
            x=alt.X("month(month):O", title=None, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("kind:N", sort=["Admissions", "Discharges"]),
            y=alt.Y("n:Q", title="People", axis=alt.Axis(tickMinStep=1, tickCount=4)),
            color=alt.Color("kind:N", scale=alt.Scale(domain=["Admissions", "Discharges"], range=[TEAL, TEAL_LIGHT]),
                            legend=alt.Legend(orient="top", title=None, direction="horizontal")),
            tooltip=[alt.Tooltip("month_label:N", title="Month"), alt.Tooltip("kind:N", title=" "),
                     alt.Tooltip("n:Q", title="People")],
        ).properties(height=220)
    )


def km_chart(curve: pd.DataFrame) -> alt.Chart:
    start = pd.DataFrame({"days": [0], "share_still_in_house": [1.0], "at_risk": [None]})
    df = pd.concat([start, curve[["days", "share_still_in_house", "at_risk"]]], ignore_index=True)
    line = _base(df).mark_line(color=BLUE, strokeWidth=2, interpolate="step-after").encode(
        x=alt.X("days:Q", title="Days since admission"),
        y=alt.Y("share_still_in_house:Q", title="Still in the house", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
        tooltip=[alt.Tooltip("days:Q", title="Day"), alt.Tooltip("share_still_in_house:Q", title="Still in the house", format=".0%"),
                 alt.Tooltip("at_risk:Q", title="People still being followed")],
    )
    half = alt.Chart(pd.DataFrame({"y": [0.5]})).mark_rule(color=MUTED, strokeDash=[4, 4]).encode(y="y:Q")
    return _fit(half + line)


def outcomes_chart(counts_by_group: pd.DataFrame, group_col: str | None = None, legend: bool = True) -> alt.Chart:
    """counts_by_group: columns outcome (raw id), n, and optionally a group column.

    legend=False when several charts share one legend (see legend_html)."""
    df = counts_by_group.copy()
    df["Outcome"] = df["outcome"].map(OUTCOME_LABELS)
    df["order"] = df["Outcome"].map({k: i for i, k in enumerate(OUTCOME_ORDER)})
    if group_col:
        df["Group"] = df[group_col].map(GROUP_LABELS).fillna(df[group_col])
    else:
        df["Group"] = "Everyone due"
    totals = df.groupby("Group")["n"].transform("sum")
    df["share"] = df["n"] / totals
    df["Group label"] = df["Group"] + " (n=" + totals.astype(int).astype(str) + ")"
    chart = (
        _base(df)
        .mark_bar(stroke="#ffffff", strokeWidth=2)
        .encode(
            y=alt.Y("Group label:N", title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X("share:Q", title="Share of everyone due", axis=alt.Axis(format=".0%", tickCount=5), stack="zero", scale=alt.Scale(domain=[0, 1])),
            color=alt.Color("Outcome:N", scale=alt.Scale(domain=OUTCOME_ORDER, range=list(OUTCOME_COLORS.values())),
                            legend=alt.Legend(orient="bottom", title=None, columns=3, labelLimit=180) if legend else None),
            order=alt.Order("order:Q"),
            tooltip=[alt.Tooltip("Group:N"), alt.Tooltip("Outcome:N"), alt.Tooltip("n:Q", title="People"),
                     alt.Tooltip("share:Q", title="Share", format=".0%")],
        )
        .properties(height=50 + 45 * df["Group"].nunique())
    )
    return _fit(chart)


def legend_html() -> str:
    """One shared legend for side-by-side outcome charts."""
    items = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:.45rem;margin:0 1.4rem .5rem 0;white-space:nowrap">'
        f'<span style="width:12px;height:12px;border-radius:3px;background:{c};display:inline-block"></span>{label}</span>'
        for label, c in OUTCOME_COLORS.items()
    )
    return f'<div style="color:{INK_2};font-size:.92rem;line-height:1.6;margin:.25rem 0 .75rem">{items}</div>'


def agent_chart(spec: QuerySpec, df: pd.DataFrame) -> alt.Chart | None:
    """Chart for an agent answer, chosen from the spec. None means show the table only."""
    chart = _agent_chart(spec, df)
    return None if chart is None else _fit(chart)


def _agent_chart(spec: QuerySpec, df: pd.DataFrame) -> alt.Chart | None:
    if spec.chart == "table" or df.empty:
        return None
    m = METRICS[spec.metric]
    if spec.metric == "occupancy":
        x = spec.group_by[0]
        d = df.assign(month=pd.to_datetime(df[x])) if x == "month" else df
        if x == "month":
            d = d.assign(partial_month=False)
            return occupancy_chart(d)
        return _simple_bar(df, x, "occupancy_rate", "Beds filled", pct=True)
    if spec.metric == "followup_outcomes":
        group = next((g for g in spec.group_by if g != "outcome"), None)
        return outcomes_chart(df, group)
    if spec.metric == "followup_engaged_rate":
        return _engaged_range_chart(df, spec.group_by[0] if spec.group_by else None)
    value = m.value_column
    if not spec.group_by:
        return None
    x = spec.group_by[0]
    color = spec.group_by[1] if len(spec.group_by) > 1 else None
    if x in ("month", "quarter", "fiscal_year") and spec.chart == "line" and color is None:
        return _base(df).mark_line(color=BLUE, strokeWidth=2, point=alt.OverlayMarkDef(size=60, filled=True, color=BLUE)).encode(
            x=alt.X(f"{x}:O", title=DIMENSIONS[x].label), y=alt.Y(f"{value}:Q", title=m.label),
            tooltip=[alt.Tooltip(f"{x}:O", title=DIMENSIONS[x].label), alt.Tooltip(f"{value}:Q", title=m.label)],
        )
    if color:
        return _base(df).mark_bar(stroke="#ffffff", strokeWidth=2).encode(
            x=alt.X(f"{x}:O", title=DIMENSIONS[x].label), y=alt.Y(f"{value}:Q", title=m.label, stack="zero"),
            color=alt.Color(f"{color}:N", title=DIMENSIONS[color].label,
                            scale=alt.Scale(range=[SAGE, SAGE_LIGHT, GREY_1, GREY_3]), legend=alt.Legend(orient="bottom")),
            tooltip=[f"{x}:O", f"{color}:N", alt.Tooltip(f"{value}:Q", title=m.label)],
        )
    return _simple_bar(df, x, value, m.label, pct=False)


def _simple_bar(df: pd.DataFrame, x: str, value: str, title: str, pct: bool) -> alt.Chart:
    horizontal = x not in ("month", "quarter", "fiscal_year")
    fmt = ".0%" if pct else "d"
    enc_val = alt.X if horizontal else alt.Y
    enc_cat = alt.Y if horizontal else alt.X
    d = df.assign(**{x: df[x].astype(str).str.replace("_", " ")}) if horizontal else df
    return _base(d).mark_bar(color=BLUE, **BAR).encode(
        **{
            ("x" if horizontal else "y"): enc_val(f"{value}:Q", title=title, axis=alt.Axis(format="%" if pct else "d")),
            ("y" if horizontal else "x"): enc_cat(f"{x}:O", title=DIMENSIONS[x].label if x in DIMENSIONS else x,
                                                  sort="-x" if horizontal else None),
        },
        tooltip=[alt.Tooltip(f"{x}:O", title=DIMENSIONS[x].label if x in DIMENSIONS else x),
                 alt.Tooltip(f"{value}:Q", title=title, format=fmt)],
    )


def _engaged_range_chart(df: pd.DataFrame, group: str | None) -> alt.Chart:
    """Confirmed engaged (solid) with the best-case range drawn as a lighter extension."""
    d = df.copy()
    d["Group"] = d[group].map(GROUP_LABELS).fillna(d[group]) if group else "Everyone due"
    d["Group"] = d["Group"] + " (n=" + d["due"].astype(int).astype(str) + ")"
    d["confirmed"] = d["engaged"] / d["due"]
    d["best"] = (d["engaged"] + d["no_outcome"]) / d["due"]
    base = _base(d).encode(y=alt.Y("Group:N", title=None, axis=alt.Axis(labelLimit=260)))
    tooltip = [alt.Tooltip("Group:N"), alt.Tooltip("confirmed:Q", title="Confirmed engaged (worst case)", format=".0%"),
               alt.Tooltip("best:Q", title="Best case", format=".0%"), alt.Tooltip("no_outcome:Q", title="No known outcome")]
    best = base.mark_bar(color="#d8e6da", **BAR).encode(
        x=alt.X("best:Q", title="Engaged in recovery, share of everyone due", axis=alt.Axis(format=".0%", tickCount=5), scale=alt.Scale(domain=[0, 1])),
        tooltip=tooltip,
    )
    confirmed = base.mark_bar(color=BLUE).encode(x="confirmed:Q", tooltip=tooltip)
    return (best + confirmed).properties(height=40 + 40 * len(d))


def share_bar(parts: list[tuple[str, int, str]], height: int = 30) -> alt.Chart:
    """One horizontal part-to-whole bar. parts: (label, count, colour) in order. Legend is drawn in HTML."""
    total = sum(n for _, n, _ in parts) or 1
    df = pd.DataFrame([{"label": l, "n": n, "share": n / total, "order": i, "color": c}
                       for i, (l, n, c) in enumerate(parts) if n])
    return _fit(
        alt.Chart(df).mark_bar(stroke="#d7d5e0", strokeWidth=1).encode(
            x=alt.X("share:Q", stack="zero", axis=None, scale=alt.Scale(domain=[0, 1])),
            color=alt.Color("color:N", scale=None, legend=None),
            order=alt.Order("order:Q"),
            tooltip=[alt.Tooltip("label:N", title=" "), alt.Tooltip("n:Q", title="People"),
                     alt.Tooltip("share:Q", title="Share", format=".0%")],
        ).properties(width=WIDTH, height=height)
    )


def share_legend(parts: list[tuple[str, int, str]]) -> str:
    """Dots with labels and counts, so identity never depends on colour alone."""
    items = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:.4rem;margin:0 1.1rem .35rem 0;white-space:nowrap">'
        f'<span style="width:9px;height:9px;border-radius:50%;background:{c};border:1px solid #d7d5e0"></span>'
        f'{l} <b style="font-weight:600">{n}</b></span>'
        for l, n, c in parts
    )
    return f'<div style="color:{INK_2};font-size:.86rem;line-height:1.5;margin:.15rem 0 .25rem">{items}</div>'
