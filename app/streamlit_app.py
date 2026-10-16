"""Harbourview analytics: one visual view for the director and funders, plus questions.

    uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import threading

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import ui

load_dotenv()

from axon.agent.definitions import DefinitionStore  # noqa: E402
from axon.agent.glossary import GLOSSARY  # noqa: E402
from axon.agent.llm import model_reachable, resolve_mode  # noqa: E402
from axon.agent.pipeline import Agent, Answer, Clarification, Session  # noqa: E402
from axon.charts import agent_chart, occupancy_chart  # noqa: E402
from axon.config import MATURITY_DAYS, FiscalYear  # noqa: E402
from axon.metrics.funnel import funnel  # noqa: E402
from axon.metrics.occupancy import monthly_occupancy  # noqa: E402
from axon.metrics.outcomes import outcomes  # noqa: E402
from axon.metrics.stays import stays  # noqa: E402
from axon.notes.review import ReviewStore  # noqa: E402
from axon.notes.schema import NOTES_DISCLOSURE, label  # noqa: E402
from axon.notes.summary import headline, summarize as summarize_notes  # noqa: E402
from axon.report.funder import render_html  # noqa: E402
from axon.status import board  # noqa: E402
from axon.tenants import TENANTS, get_tenant  # noqa: E402
from axon.warehouse import build_all, load  # noqa: E402

st.set_page_config(page_title="Harbourview analytics", layout="wide", initial_sidebar_state="collapsed")
st.markdown(ui.CSS, unsafe_allow_html=True)

EXAMPLES = [
    "How many admissions did we have each month in 2025?",
    "How full was the house each month in 2025?",
    "What percentage of residents were sober at 6 months?",
    "How many active residents do we have, by phase?",
]
# The identity provider sets the house in production. The generated test house exists only for the tests.
SESSION = Session("harbourview", "director@harbourview")
FIELD_COLOR = {"referral": ui.BLUE, "discharge": ui.VIOLET, "destination": ui.SAGE, "engagement": ui.SAGE,
               "risk": ui.ORANGE, "passes": ui.BLUE}


@st.cache_resource
def get_agent() -> Agent:
    agent = Agent()
    agent.llm.timeout_s = 90  # interactive: fail politely instead of hanging
    threading.Thread(target=agent.llm.warm_up, daemon=True).start()
    return agent


@st.cache_resource
def ensure_built() -> bool:
    if any(t.csv_path.exists() and not t.warehouse_path.exists() for t in TENANTS.values()):
        build_all()
    return True


@st.cache_data
def get_warehouse(tenant_id: str):
    return load(get_tenant(tenant_id))


def show(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)


def days(v) -> str:
    return "–" if v is None or pd.isna(v) else f"{v:.0f}"


def pct(n: int, d: int) -> str:
    return "–" if not d else f"{100 * n / d:.0f}"


# ---------------------------------------------------------------- header
ensure_built()
session = SESSION
agent = get_agent()
tenant = get_tenant(session.tenant_id)
w = get_warehouse(session.tenant_id)
decisions = ReviewStore().decisions(session.tenant_id)
head, fy_col, export_col = st.columns([6, 1.3, 1.3], vertical_alignment="bottom")
with fy_col:
    fy = FiscalYear(st.selectbox("Fiscal year", [2025, 2024], format_func=lambda y: f"FY{y}" + (" (Jul–Dec)" if y == 2024 else "")))
with head:
    show(f'<p class="ax-name">{tenant.name}</p><p class="ax-meta">As of {w.as_of:%d %b %Y}, Jan–Dec fiscal year, synthetic data</p>')
with export_col:
    st.download_button("Export", render_html(session.tenant_id, fy.year), file_name=f"{session.tenant_id}_{fy.label}_report.html",
                       mime="text/html", help="Funder report: counts from 1 to 4 hidden. Print to PDF from the browser.",
                       width="stretch", icon=":material/download:")

flags = {f.key: f for f in board(w, decisions)}
show(ui.strip([
    ("bed", ui.SAGE, flags["beds"].value, f"in the house, {flags['beds'].detail.replace(' beds', '')}"),
    ("inbox", ui.BLUE, flags["waiting"].value, f"waiting for intake (notes: {flags['waiting'].detail.replace('notes say ', '')})"),
    ("phone", ui.ORANGE, flags["calls"].value, "calls due in 30 days"),
    ("file", ui.VIOLET, flags["missing"].value, "follow-ups not recorded"),
]))
if flags["beds"].status == "red":
    st.markdown(f":red-badge[:material/error: {flags['beds'].badge}: {flags['beds'].detail}]")

tab_flow, tab_occ, tab_out, tab_notes, tab_ask = st.tabs(["Flow", "Occupancy", "Outcomes", "Notes", "Ask"])
f = funnel(w.residents, fy, w.as_of)
occ = monthly_occupancy(w.nightly_census, fy)
s = stays(w.residents, fy)
o6, o12 = outcomes(w.followups, 6), outcomes(w.followups, 12)

# ---------------------------------------------------------------- flow
with tab_flow:
    t = f.timings
    gaps = [f"median {days(t['Referral to intake'].median)} days, P90 {days(t['Referral to intake'].p90)}",
            f"median {days(t['Intake to admission'].median)} days, P90 {days(t['Intake to admission'].p90)}"]
    stages = [("Referred", f.matured_n, str(f.matured_n)),
              ("Intake", f.stages[1].n, f"{f.stages[1].n} ({pct(f.stages[1].n, f.matured_n)}%)"),
              ("Admitted", f.overall.n, f"{f.overall.n} ({pct(f.overall.n, f.matured_n)}%)")]
    excluded = ", ".join(f"{n} from {k.lower()}" for k, n in f.timing_exclusions.items() if n)
    body = ui.funnel(stages, gaps) + ui.sub(
        f'Referral to admission: median {days(t["Referral to admission"].median)} days, P90 '
        f'{days(t["Referral to admission"].p90)}. {f.cohort_n - f.matured_n} recent referrals not counted yet.')
    show(ui.card("Referral → intake → admission", body,
                 tip=f"Referrals made by {f.cutoff:%d %b %Y}, so each had {MATURITY_DAYS}+ days to progress; later ones are "
                     f"too recent to judge. Times are for people who moved on. Left out of timings (dates missing or out of "
                     f"order): {excluded or 'none'}. Percentages are of everyone referred."))
    not_admitted = w.residents[(w.residents["referral_fy"] == fy.year) & ~w.residents["admitted"]]
    counts = not_admitted["note_referral"].fillna("no usable note").value_counts()
    open_ = {"pending_intake", "waitlisted"}
    rows = [(label(k) + (" (open)" if k in open_ else ""), v,
             ui.BLUE if k in open_ else (ui.GREY_3 if k == "no usable note" else ui.ORANGE), f"{v} ({pct(v, len(not_admitted))}%)")
            for k, v in counts.items()]
    show(ui.card("Why referrals weren't admitted", ui.hbars(rows) + ui.sub(f"{len(not_admitted)} referrals not admitted. Read from staff notes."),
                 tip=NOTES_DISCLOSURE))

# ---------------------------------------------------------------- occupancy
with tab_occ:
    show(ui.tiles([
        ("Beds filled", pct(occ.bed_nights, occ.capacity_nights), " %", f"{occ.bed_nights:,} of {occ.capacity_nights:,} bed-nights"),
        ("Typical stay", days(s.km_median_days), " days", "counting stays still open"),
        ("Still in the house", str(s.ongoing.n), "", f"{days(s.ongoing.median)} days so far (median)"),
    ]))
    tip = (f"{w.capacity} beds. Counted per night: a bed is filled from admission up to, not including, discharge. "
           "The axis starts above zero to show the month-to-month change.")
    if occ.estimated_bed_nights:
        tip += (f" {occ.estimated_bed_nights} bed-nights use estimated discharge dates (admission + "
                f"{w.meta['estimated_stay_days']:.0f} days) for people with none recorded.")
    if occ.monthly["month"].min() < pd.Timestamp("2025-04-01"):
        tip += " Months before April 2025 may read low: the file starts in July 2024."
    with st.container(border=True):
        show(ui.title_row("Monthly occupancy", tip))
        st.altair_chart(occupancy_chart(occ.monthly), width="stretch")
    fin = s.finished.set_index("group")
    rows = []
    for g, col in [("Completed the program", ui.SAGE), ("Left early (all reasons)", ui.ORANGE)]:
        if g in fin.index:
            rows.append((g.replace(" (all reasons)", ""), float(fin.loc[g, "median_days"]), col,
                         f"{days(fin.loc[g, 'median_days'])} days (P90 {days(fin.loc[g, 'p90_days'])}, n={int(fin.loc[g, 'n'])})"))
    rows.append(("Still in the house", float(s.ongoing.median or 0), ui.BLUE,
                 f"{days(s.ongoing.median)} days so far (n={s.ongoing.n})"))
    show(ui.card("Length of stay (median days)", ui.hbars(rows) +
                 ui.sub(f"Admitted in {fy.label}. Typical stay {days(s.km_median_days)} days counts open stays; "
                        f"finished stays alone: {days(s.finished_all.median)}."),
                 tip=f"Kaplan-Meier counts people still in the house as “at least this long”. {s.missing_discharge_date} "
                     "stays with no discharge date are left out of length of stay."))

# ---------------------------------------------------------------- outcomes
with tab_out:
    cohort = w.residents[w.residents["admitted"] & (w.residents["admission_fy"] == fy.year)]
    ex = cohort["exit_type"].value_counts()
    completed = int(ex.get("completed", 0))
    show(ui.tiles([
        ("Completed", pct(completed, len(cohort)), " %", f"{completed} of {len(cohort)} admitted"),
        ("Engaged at 6 months", f"{100 * o6.engaged_worst_case:.0f}–{100 * o6.engaged_best_case:.0f}", " %",
         f"worst to best case, {o6.due_n} due"),
        ("Engaged at 12 months", f"{100 * o12.engaged_worst_case:.0f}–{100 * o12.engaged_best_case:.0f}", " %",
         f"{o12.due_n} due, too few to judge" if o12.due_n < 20 else f"worst to best case, {o12.due_n} due"),
    ]))
    exit_parts = [("Completed", int(ex.get("completed", 0)), ui.SAGE), ("Transferred", int(ex.get("transferred", 0)), ui.BLUE),
                  ("Left by choice", int(ex.get("left_by_choice", 0)), ui.ORANGE),
                  ("Discharged by house", int(ex.get("discharged_by_house", 0)), ui.VIOLET),
                  ("Custody", int(ex.get("custody", 0)), ui.GREY_1), ("Other or unknown", int(ex.get("other_or_unknown", 0)), ui.GREY_2),
                  ("Still in program", int(ex.get("still_in_program", 0)), ui.LIGHT)]
    from_notes = int(cohort["exit_from_notes"].sum())
    c1, c2 = st.columns([3, 2], gap="medium")
    with c1:
        show(ui.card("How stays ended", ui.seg_bar(exit_parts) + ui.sub(f"{len(cohort)} people admitted in {fy.label}"),
                     tip="Completion is counted separately from discharge. The recorded reason comes first"
                         + (f"; {from_notes} reasons recorded as “other” or blank were filled in from staff notes "
                            "(AI-assisted; not used in the funder report)." if from_notes else ".")))
    with c2:
        left = cohort[cohort["exit_type"] != "still_in_program"]
        dest = left["destination"].fillna("not stated").value_counts()
        rows = [(label(k), v, ui.GREY_3 if k == "not stated" else ui.SAGE, str(v)) for k, v in dest.items()]
        show(ui.card("Where people went next", ui.hbars(rows) + ui.sub(f"{len(left)} people who have left. Read from staff notes."),
                     tip=NOTES_DISCLOSURE))
    for r in (o6, o12):
        c = r.counts
        parts = [("Engaged in recovery", c["engaged_in_recovery"], ui.SAGE), ("Lost to follow-up", c["lost_to_follow_up"], ui.GREY_1),
                 ("Unknown", c["unknown"], ui.GREY_2), ("Not recorded", c["not_recorded"], ui.GREY_3),
                 ("Relapse reported", c["relapse_reported"], ui.ORANGE)]
        worst, best = 100 * r.engaged_worst_case, 100 * r.engaged_best_case
        span = (worst, best, f"Engaged: {worst:.0f}% (worst case) to {best:.0f}% (best case)")
        show(ui.card(f"{r.horizon_months}-month follow-up", ui.seg_bar(parts, span) +
                     ui.sub(f"{r.due_n} people due" + (", too few to judge" if r.due_n < 20 else "")),
                     tip="Everyone whose follow-up date has passed counts, including people who left early; all years "
                         "pooled. Worst case: nobody we couldn't reach is engaged. Best case: all of them are. Never "
                         "reported only among people reached."))

# ---------------------------------------------------------------- notes
with tab_notes:
    hl = headline(w.residents, w.note_findings)
    show(ui.tiles([(k, str(n), f" of {d}", "in the house now") for k, (n, d) in hl.items()], cols=4))
    groups = summarize_notes(w.residents, w.note_findings)
    cols = st.columns(2, gap="medium")
    for i, g in enumerate(groups):
        rows = [(label(v), n, FIELD_COLOR.get(fl, ui.GREY_2), f"{n} ({sh:.0%})") for fl, v, n, sh in g.table.itertuples(index=False)]
        with cols[i % 2]:
            show(ui.card(g.name, (ui.hbars(rows, scale=g.people) if rows else ui.sub("Nothing found in these notes.", "0"))
                         + ui.sub(f"{g.people} people"),
                         tip=NOTES_DISCLOSURE + f" {g.with_finding} of {g.people} have a usable note."
                             + (" No note in this file mentions a pass." if g.name == "In the house now" and hl["Passes mentioned"][0] == 0 else "")))

# ---------------------------------------------------------------- ask
with tab_ask:
    live = model_reachable() and resolve_mode() != "replay"
    turns_key = f"turns_{session.tenant_id}"
    st.session_state.setdefault(turns_key, [])
    turns: list[dict] = st.session_state[turns_key]

    def ask(q: str) -> None:
        with st.spinner("Working on it. The local model usually takes about 10 seconds."):
            turns.append({"question": q, "result": agent.ask(q, session)})

    st.caption("Totals only. A self-hosted model turns your question into a checked, read-only query; it never sees "
               "resident records." + ("" if live else " Local model off: recorded answers only."))
    ex_cols = st.columns(4, gap="small")
    for i, q in enumerate(EXAMPLES):
        if ex_cols[i].button(q, key=f"ex_{i}", width="stretch"):
            ask(q)

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
                    st.caption(f":material/bookmark: “{d.term}” = {d.label}")
                st.caption(f":material/smart_toy: {r.disclosure}")
                with st.expander("Spec, query and data"):
                    st.json(r.executed.model_dump(mode="json"), expanded=False)
                    st.code(r.sql, language="sql")
                    st.dataframe(r.frame, hide_index=True, width="stretch")
                    for c in r.caveats:
                        st.caption(c)
            elif isinstance(r, Clarification):
                st.markdown(f":orange-badge[:material/help: Needs a definition] **{r.question}**  \n{r.why}")
                if turn.get("answered"):
                    st.caption(f"You chose: {turn['answered']}")
                else:
                    for c in r.choices:
                        if st.button(c.label, key=f"choice_{idx}_{c.id}"):
                            agent.define(session, r.term, c.id)
                            turn["answered"] = c.label
                            ask(turn["question"])
                            st.rerun()
            else:
                st.markdown(f":gray-badge[:material/block: Not answered] {r.message}")

    for i, turn in enumerate(turns):
        render(turn, i)
    with st.expander("House definitions"):
        current = DefinitionStore().current(session.tenant_id)
        if not current:
            st.caption("None yet. " + ", ".join(f"“{t}”" for t in sorted(GLOSSARY)) + " are asked about the first time.")
        for term, d in sorted(current.items()):
            a, b = st.columns([6, 1], vertical_alignment="center")
            a.markdown(f"**{term}**: {d.label}  \n:gray[version {d.version}]")
            if b.button("Reset", key=f"reset_{term}"):
                DefinitionStore().save(session.tenant_id, term, None, session.user_id)
                st.rerun()
    q = st.chat_input("Ask about your house")
    if q:
        ask(q)
        st.rerun()
