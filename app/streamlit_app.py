"""Harbourview analytics: one view for the director and funders, plus questions and staff notes.

    uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from axon.agent.definitions import DefinitionStore  # noqa: E402
from axon.agent.glossary import GLOSSARY  # noqa: E402
from axon.agent.llm import model_reachable, resolve_mode  # noqa: E402
from axon.agent.pipeline import Agent, Answer, Clarification, Session  # noqa: E402
from axon.charts import EXIT_COLORS, OUTCOME_COLORS, agent_chart, occupancy_chart, share_bar, share_legend  # noqa: E402
from axon.config import MATURITY_DAYS, FiscalYear  # noqa: E402
from axon.metrics.funnel import funnel  # noqa: E402
from axon.metrics.occupancy import monthly_occupancy  # noqa: E402
from axon.metrics.outcomes import OUTCOME_LABELS, outcomes  # noqa: E402
from axon.metrics.stays import stays  # noqa: E402
from axon.notes.review import ReviewStore  # noqa: E402
from axon.notes.schema import NOTES_DISCLOSURE, label  # noqa: E402
from axon.report.funder import render_html  # noqa: E402
from axon.status import STATUS_ICON, board, review_queue  # noqa: E402
from axon.tenants import TENANTS, get_tenant  # noqa: E402
from axon.warehouse import build_all, load  # noqa: E402

st.set_page_config(page_title="Harbourview analytics", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    """
    <style>
    .block-container { max-width: 1180px; padding-top: 2.6rem; padding-bottom: 3rem; }
    [data-testid="stSidebarCollapsedControl"] { display: none; }
    [data-testid="stMarkdownContainer"] p { line-height: 1.6; }
    .hdr-name { font-size: 1.3rem; font-weight: 600; color: #030302; margin: 0; }
    .hdr-meta { color: #54586b; font-size: .85rem; margin: .1rem 0 0; }
    .lab { font-size: .7rem; letter-spacing: .07em; text-transform: uppercase; color: #7e7d91; }
    .tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; margin: .25rem 0 .9rem; }
    .tile { background: #fff; border: 1px solid #eceaf2; border-radius: 10px; padding: .8rem 1rem; }
    .val { font-size: 1.65rem; font-weight: 500; color: #030302; margin-top: .1rem; font-variant-numeric: tabular-nums; }
    .unit { font-size: .85rem; color: #54586b; font-weight: 400; }
    .sub { font-size: .8rem; color: #54586b; margin-top: .1rem; }
    .foot { font-size: .8rem; color: #7e7d91; border-top: 1px solid #f0f0f3; margin-top: .6rem; padding-top: .5rem; }
    .st-key-strip { background: #fff; border: 1px solid #eceaf2; border-radius: 10px; padding: .7rem .9rem .3rem; margin-bottom: .4rem; }
    .st-key-strip [data-testid="stColumn"] + [data-testid="stColumn"] { border-left: 1px solid #f0f0f3; padding-left: .9rem; }
    .k-value { font-size: 1.35rem; font-weight: 500; color: #030302; font-variant-numeric: tabular-nums; line-height: 1.3; }
    table.t { width: 100%; border-collapse: collapse; font-size: .88rem; font-variant-numeric: tabular-nums; border: 0 !important; }
    table.t th, table.t td { border: 0 !important; border-bottom: 1px solid #f0f0f3 !important; padding: .45rem .4rem; text-align: left; background: transparent !important; }
    table.t th { font-size: .7rem; letter-spacing: .06em; text-transform: uppercase; color: #7e7d91; font-weight: 500; }
    table.t td.r, table.t th.r { text-align: right; }
    [data-testid="stVerticalBlockBorderWrapper"] { background: #fff; }
    </style>
    """,
    unsafe_allow_html=True,
)

EXAMPLES = [
    "How many admissions did we have each month in 2025?",
    "How full was the house each month in 2025?",
    "What percentage of residents were sober at 6 months?",
    "How many active residents do we have, by phase?",
]
# Demo sign-in. In production the identity provider sets the house; nothing typed can change it.
HOUSES = {"Harbourview House": Session("harbourview", "director@harbourview"),
          "Northshore Youth Residence": Session("northshore", "director@northshore")}
BADGE = {"red": "red", "amber": "orange", "green": "green"}


@st.cache_resource
def get_agent() -> Agent:
    return Agent()


@st.cache_resource
def ensure_built() -> bool:
    if any(t.csv_path.exists() and not t.warehouse_path.exists() for t in TENANTS.values()):
        build_all()
    return True


@st.cache_data
def get_warehouse(tenant_id: str):
    return load(get_tenant(tenant_id))


def days(v) -> str:
    return "–" if v is None or pd.isna(v) else f"{v:.0f}"


def pct_num(n: int, d: int) -> str:
    return "–" if not d else f"{100 * n / d:.0f}"


def tiles(items: list[tuple[str, str, str, str]]) -> None:
    """(label, value, unit, sub)"""
    st.markdown('<div class="tiles">' + "".join(
        f'<div class="tile"><div class="lab">{l}</div><div class="val">{v}<span class="unit">{u}</span></div>'
        f'<div class="sub">{s}</div></div>' for l, v, u, s in items) + "</div>", unsafe_allow_html=True)


def table(headers: list[str], rows: list[list], right_from: int = 1) -> str:
    th = "".join(f'<th class="{"r" if i >= right_from else ""}">{h}</th>' for i, h in enumerate(headers))
    tr = "".join("<tr>" + "".join(f'<td class="{"r" if i >= right_from else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>"
                 for r in rows)
    return f'<table class="t"><tr>{th}</tr>{tr}</table>'


def card_title(text: str) -> None:
    st.markdown(f'<div class="lab" style="margin-bottom:.4rem">{text}</div>', unsafe_allow_html=True)


def foot(text: str) -> None:
    st.markdown(f'<div class="foot">{text}</div>', unsafe_allow_html=True)


def rng(lo: float | None, hi: float | None) -> str:
    return "–" if lo is None or hi is None else f"{100 * lo:.0f}–{100 * hi:.0f}"


# ---------------------------------------------------------------- header
ensure_built()
head, house_col, fy_col, export_col = st.columns([4.2, 2, 1.2, 1.6], vertical_alignment="bottom")
with house_col:
    session = HOUSES[st.selectbox("House (demo sign-in)", list(HOUSES))]
with fy_col:
    fy = FiscalYear(st.selectbox("Fiscal year", [2025, 2024], format_func=lambda y: f"FY{y}" + (" (Jul–Dec)" if y == 2024 else "")))
tenant = get_tenant(session.tenant_id)
w = get_warehouse(session.tenant_id)
reviews = ReviewStore()
decisions = reviews.decisions(session.tenant_id)
with head:
    st.markdown(f'<p class="hdr-name">{tenant.name}</p><p class="hdr-meta">Data as of {w.as_of:%d %b %Y} · '
                f'January–December fiscal year · synthetic data</p>', unsafe_allow_html=True)
with export_col:
    st.download_button("Export report", render_html(session.tenant_id, fy.year),
                       file_name=f"{session.tenant_id}_{fy.label}_funder_report.html", mime="text/html",
                       help="Counts from 1 to 4 are hidden. Print to PDF from the browser if needed.", width="stretch")

# ---------------------------------------------------------------- status strip
flags = [f for f in board(w, decisions) if f.key != "data"]
with st.container(key="strip"):
    for col, fl in zip(st.columns(len(flags), gap="small"), flags):
        with col:
            st.markdown(f'<div class="lab">{fl.label}</div><div class="k-value">{fl.value}</div>', unsafe_allow_html=True)
            st.markdown(f":{BADGE[fl.status]}-badge[:material/{STATUS_ICON[fl.status]}: {fl.badge}]")

tab_flow, tab_occ, tab_out, tab_ask, tab_notes = st.tabs(["Flow", "Occupancy and stay", "Outcomes", "Ask", "Staff notes"])
f = funnel(w.residents, fy, w.as_of)
occ = monthly_occupancy(w.nightly_census, fy)
s = stays(w.residents, fy)
o6, o12 = outcomes(w.followups, 6), outcomes(w.followups, 12)

# ---------------------------------------------------------------- flow
with tab_flow:
    reached, admitted = f.stages[1], f.overall
    tiles([("Referred", str(f.matured_n), "", f"in {fy.label}, with {MATURITY_DAYS}+ days to progress"),
           ("Reached intake", pct_num(reached.n, reached.of), " %", f"{reached.n} of {reached.of}"),
           ("Admitted", pct_num(admitted.n, admitted.of), " %", f"{admitted.n} of {admitted.of}")])
    with st.container(border=True):
        card_title("Time in each step · people who moved on")
        st.markdown(table(["Step", "People", "Median days", "P90 days"],
                          [[k, v.n, days(v.median), days(v.p90)] for k, v in f.timings.items()]), unsafe_allow_html=True)
        excluded = [f"{n} from {k.lower()}" for k, n in f.timing_exclusions.items() if n]
        foot(f"{f.cohort_n - f.matured_n} referrals after {f.cutoff:%d %b %Y} are too recent to judge and are not in these rates."
             + (f" Left out of timings (dates missing or out of order): {', '.join(excluded)}." if excluded else ""))
    not_admitted = w.residents[(w.residents["referral_fy"] == fy.year) & ~w.residents["admitted"]]
    with st.expander(f"Why {len(not_admitted)} referrals weren't admitted · from staff notes"):
        counts = not_admitted["note_referral"].fillna("no usable note").value_counts()
        state = {"pending_intake": "open", "waitlisted": "open", "no usable note": "–"}
        st.markdown(table(["Note says", "Open or closed", "Referrals"],
                          [[label(k), state.get(k, "closed"), v] for k, v in counts.items()], right_from=2),
                    unsafe_allow_html=True)
        foot(NOTES_DISCLOSURE)

# ---------------------------------------------------------------- occupancy and stay
with tab_occ:
    tiles([("Beds filled", pct_num(occ.bed_nights, occ.capacity_nights), " %", f"{occ.bed_nights:,} of {occ.capacity_nights:,} bed-nights"),
           ("Typical stay", days(s.km_median_days), " days", f"admitted in {fy.label}, counting open stays"),
           ("Still in the house", str(s.ongoing.n), "", f"{days(s.ongoing.median)} days so far (median)")])
    with st.container(border=True):
        card_title(f"Monthly occupancy against {w.capacity} beds")
        st.altair_chart(occupancy_chart(occ.monthly), width="stretch")
        notes = ["Counted per night: a bed is filled from admission up to, not including, discharge."]
        if occ.estimated_bed_nights:
            notes.append(f"{occ.estimated_bed_nights} bed-nights use estimated discharge dates (admission + "
                         f"{w.meta['estimated_stay_days']:.0f} days).")
        if occ.monthly["month"].min() < pd.Timestamp("2025-04-01"):
            notes.append("Months before April 2025 may read low: the file starts in July 2024.")
        foot(" ".join(notes))
    with st.container(border=True):
        card_title(f"Length of stay · {s.admitted_n} admitted in {fy.label}")
        fin = s.finished.set_index("group")
        rows = [[g, int(fin.loc[g, "n"]), days(fin.loc[g, "median_days"]), days(fin.loc[g, "p90_days"])]
                for g in ["Completed the program", "Left early (all reasons)"] if g in fin.index]
        rows.append(["Still in the house (days so far)", s.ongoing.n, days(s.ongoing.median), days(s.ongoing.p90)])
        st.markdown(table(["Stays", "People", "Median days", "P90 days"], rows), unsafe_allow_html=True)
        foot(f"Typical stay ({days(s.km_median_days)} days) counts open stays as “at least this long” (Kaplan-Meier); "
             f"finished stays alone would say {days(s.finished_all.median)}. "
             f"{s.missing_discharge_date} stays with no discharge date are left out.")

# ---------------------------------------------------------------- outcomes
with tab_out:
    cohort = w.residents[w.residents["admitted"] & (w.residents["admission_fy"] == fy.year)]
    ex = cohort["exit_type"].value_counts()
    exit_parts = [(EXIT_COLORS[k][0], int(ex.get(k, 0)), EXIT_COLORS[k][1]) for k in EXIT_COLORS if ex.get(k, 0)]
    completed = int(ex.get("completed", 0))
    tiles([("Completed", pct_num(completed, len(cohort)), " %", f"{completed} of {len(cohort)} admitted in {fy.label}"),
           ("Engaged at 6 months", rng(o6.engaged_worst_case, o6.engaged_best_case), " %", f"worst to best case · {o6.due_n} due"),
           ("Engaged at 12 months", rng(o12.engaged_worst_case, o12.engaged_best_case), " %",
            f"{o12.due_n} due · too few to judge" if o12.due_n < 20 else f"worst to best case · {o12.due_n} due")])
    with st.container(border=True):
        card_title(f"How stays ended · {len(cohort)} admitted in {fy.label}")
        st.altair_chart(share_bar(exit_parts), width="stretch")
        st.markdown(share_legend(exit_parts), unsafe_allow_html=True)
        left = cohort[cohort["exit_type"] != "still_in_program"]
        dest = left["destination"].fillna("not stated").value_counts()
        st.markdown('<div class="sub" style="margin-top:.4rem"><span class="lab">Where they went next · from notes</span>&nbsp; '
                    + " · ".join(f"{label(k)} <b>{v}</b>" for k, v in dest.items()) + "</div>", unsafe_allow_html=True)
        from_notes = int(cohort["exit_from_notes"].sum())
        foot("Completion is counted separately from discharge. The recorded reason is used first"
             + (f"; {from_notes} reasons recorded as “other” or blank were filled in from staff notes." if from_notes else ".")
             + " Values from notes are AI-assisted and await staff review.")
    with st.container(border=True):
        for r in (o6, o12):
            parts = [(OUTCOME_LABELS[k], v, OUTCOME_COLORS[OUTCOME_LABELS[k]]) for k, v in r.counts.items()]
            card_title(f"{r.horizon_months}-month follow-up · {r.due_n} due" + (" · too few to judge" if r.due_n < 20 else ""))
            st.altair_chart(share_bar(parts), width="stretch")
            st.markdown(share_legend(parts), unsafe_allow_html=True)
        foot("Everyone whose follow-up date has passed counts, including people who left early; all years pooled. "
             "Worst case: nobody we couldn't reach is engaged. Best case: all of them are. "
             "Outcomes are never reported only among people we reached.")

# ---------------------------------------------------------------- ask
with tab_ask:
    agent = get_agent()
    live = model_reachable() and resolve_mode() != "replay"
    turns_key = f"turns_{session.tenant_id}"
    st.session_state.setdefault(turns_key, [])
    turns: list[dict] = st.session_state[turns_key]
    st.caption("Totals only. A self-hosted model turns your question into a checked, read-only query; it never sees "
               "resident records. " + ("Local model running." if live else "Local model off: replaying recorded answers."))
    ex_cols = st.columns(4, gap="small")
    for i, q in enumerate(EXAMPLES):
        if ex_cols[i].button(q, key=f"ex_{i}", width="stretch"):
            turns.append({"question": q, "result": agent.ask(q, session)})

    def render(turn: dict, idx: int) -> None:
        r = turn["result"]
        with st.chat_message("user", avatar=":material/person:"):
            st.markdown(turn["question"])
        with st.chat_message("assistant", avatar=":material/query_stats:"):
            if isinstance(r, Answer):
                st.markdown(r.text)
                chart = agent_chart(r.spec, r.frame)
                if chart is not None:
                    st.altair_chart(chart, width="stretch")
                for d in r.definitions:
                    st.caption(f":material/bookmark: Using {tenant.name}'s definition of “{d.term}”: {d.label} (version {d.version}).")
                for c in r.caveats:
                    st.caption(c)
                st.caption(f":material/smart_toy: {r.disclosure}")
                with st.expander("Spec, query and data"):
                    st.json(r.executed.model_dump(mode="json"), expanded=False)
                    st.code(r.sql, language="sql")
                    st.caption(f"Parameters {r.params} · spec {r.executed.hash} · audit {r.event_id}")
                    st.dataframe(r.frame, hide_index=True, width="stretch")
            elif isinstance(r, Clarification):
                st.markdown(f":orange-badge[:material/help: Needs a definition] **{r.question}**  \n{r.why}")
                if turn.get("answered"):
                    st.caption(f"You chose: {turn['answered']}")
                else:
                    for c in r.choices:
                        if st.button(c.label, key=f"choice_{session.tenant_id}_{idx}_{c.id}"):
                            agent.define(session, r.term, c.id)
                            turn["answered"] = c.label
                            turns.append({"question": turn["question"], "result": agent.ask(turn["question"], session)})
                            st.rerun()
                    st.caption(f"Saved as {tenant.name}'s definition and named under every answer that uses it.")
            else:
                st.markdown(f":gray-badge[:material/block: Not answered] {r.message}")

    for i, t in enumerate(turns):
        render(t, i)
    with st.expander(f"{tenant.name} definitions"):
        current = DefinitionStore().current(session.tenant_id)
        if not current:
            st.caption("None yet. Words like " + ", ".join(f"“{t}”" for t in sorted(GLOSSARY)) + " are asked about the first time.")
        for term, d in sorted(current.items()):
            a, b = st.columns([6, 1], vertical_alignment="center")
            a.markdown(f"**{term}**: {d.label}  \n:gray[version {d.version}, set by {d.defined_by}]")
            if b.button("Reset", key=f"reset_{session.tenant_id}_{term}"):
                DefinitionStore().save(session.tenant_id, term, None, session.user_id)
                st.rerun()
    q = st.chat_input("Ask about your house")
    if q:
        turns.append({"question": q, "result": agent.ask(q, session)})
        st.rerun()

# ---------------------------------------------------------------- staff notes
with tab_notes:
    st.caption(NOTES_DISCLOSURE + " Notes are redacted before anything reads them; every value quotes the words it came from.")
    queue = review_queue(w, decisions)
    c1, c2 = st.columns([3, 2], gap="medium")
    with c1, st.container(border=True):
        card_title(f"Review queue · {len(queue)} · risk flags first")
        if queue.empty:
            st.markdown(":green-badge[:material/check_circle: Up to date] Nothing waiting for review.")
        for row in queue.head(12).itertuples():
            a, b, c = st.columns([4, 1.4, 1.3], vertical_alignment="center")
            tag = ":orange-badge[:material/warning: risk]" if row.field == "risk" else f":gray-badge[{row.field}]"
            a.markdown(f"{tag} **{label(row.value)}** · {row.resident_id}  \n:gray[“{html.escape(row.quote)}” · {row.source}]")
            if b.button("Confirm", key=f"ok_{session.tenant_id}_{row.key}"):
                reviews.decide(session.tenant_id, row.resident_id, row.field, row.value, "confirm", session.user_id)
                st.rerun()
            if c.button("Reject", key=f"no_{session.tenant_id}_{row.key}"):
                reviews.decide(session.tenant_id, row.resident_id, row.field, row.value, "reject", session.user_id)
                st.rerun()
        if len(queue) > 12:
            st.caption(f"{len(queue) - 12} more in the queue.")
    with c2, st.container(border=True):
        card_title("What the notes add · people")
        nf = w.note_findings
        summary = nf.assign(v=nf["value"].map(label)).groupby(["field", "v"])["resident_id"].nunique().reset_index()
        st.markdown(table(["Field", "Value", "People"], summary.values.tolist(), right_from=2), unsafe_allow_html=True)
