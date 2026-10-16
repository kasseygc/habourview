"""Harbourview analytics: status board, natural-language questions, funder export.

    uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

from axon.agent.definitions import DefinitionStore  # noqa: E402
from axon.agent.glossary import GLOSSARY  # noqa: E402
from axon.agent.llm import model_reachable, resolve_mode  # noqa: E402
from axon.agent.pipeline import Agent, Answer, Clarification, Session  # noqa: E402
from axon.charts import (  # noqa: E402
    agent_chart, census_chart, flow_chart, funnel_chart, km_chart, legend_html, occupancy_chart, outcomes_chart,
)
from axon.config import MATURITY_DAYS, FiscalYear  # noqa: E402
from axon.metrics.funnel import funnel  # noqa: E402
from axon.metrics.occupancy import monthly_occupancy  # noqa: E402
from axon.metrics.outcomes import OUTCOME_LABELS, outcomes  # noqa: E402
from axon.metrics.stays import stays  # noqa: E402
from axon.report.funder import render_html  # noqa: E402
from axon.notes.review import ReviewStore  # noqa: E402
from axon.notes.schema import FIELDS, label  # noqa: E402
from axon.status import STATUS_ICON, board, review_queue  # noqa: E402
from axon.tenants import TENANTS, get_tenant  # noqa: E402
from axon.warehouse import build_all, load  # noqa: E402

st.set_page_config(page_title="Harbourview analytics", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    .block-container { max-width: 1200px; padding-top: 3rem; padding-bottom: 4rem; }
    [data-testid="stSidebarCollapsedControl"] { display: none; }
    [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li { line-height: 1.65; }
    [data-testid="stCaptionContainer"] { line-height: 1.55; }
    .hdr-name { font-size: 1.45rem; font-weight: 600; color: #1E293B; margin: 0; letter-spacing: -0.01em; }
    .hdr-meta { color: #475569; font-size: .9rem; margin: .2rem 0 0; }
    .k-label { color: #475569; font-size: .85rem; margin-bottom: .15rem; }
    .k-value { font-size: 1.9rem; font-weight: 600; color: #1E293B; font-variant-numeric: tabular-nums; line-height: 1.2; }
    .k-unit { font-size: 1rem; font-weight: 400; color: #475569; }
    .st-key-strip [data-testid="stColumn"] + [data-testid="stColumn"] { border-left: 1px solid #E2E8F0; padding-left: 1.25rem; }
    .st-key-strip { border-top: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0; padding: 1rem 0 .75rem; }
    .sec { font-size: .95rem; font-weight: 600; color: #1E293B; margin: 0 0 .25rem; }
    .sec-sub { color: #475569; font-size: .85rem; margin: 0 0 .5rem; }
    table.glance { width: 100%; border-collapse: collapse; font-size: .92rem; font-variant-numeric: tabular-nums; border: 0 !important; }
    table.glance th, table.glance td { border-left: 0 !important; border-right: 0 !important; border-top: 0 !important; background: transparent !important; }
    table.glance th { text-align: left; color: #475569; font-weight: 500; padding: .55rem .6rem; border-bottom: 1px solid #CBD5E1; }
    table.glance td { padding: .6rem .6rem; border-bottom: 1px solid #E2E8F0; vertical-align: top; }
    table.glance td.num { text-align: right; font-weight: 600; white-space: nowrap; }
    table.glance td.base { color: #475569; }
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
# Demo sign-in. In production the role and house come from the identity provider.
SIGN_INS = {
    "Director · Harbourview House": Session("harbourview", "director@harbourview", "director"),
    "Funder · Harbourview House": Session("harbourview", "funder@harbourview", "funder"),
    "Director · Northshore Youth Residence": Session("northshore", "director@northshore", "director"),
}
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


def fmt_days(v: float | None) -> str:
    return "–" if v is None or pd.isna(v) else f"{v:.0f}"


def section(title: str, sub: str | None = None) -> None:
    st.markdown(f'<p class="sec">{title}</p>' + (f'<p class="sec-sub">{sub}</p>' if sub else ""), unsafe_allow_html=True)


# ---------------------------------------------------------------- header and filters
ensure_built()
head, who_col, fy_col = st.columns([5, 2.2, 1.3], vertical_alignment="bottom")
with who_col:
    who = st.selectbox("Signed in as (demo)", list(SIGN_INS))
session = SIGN_INS[who]
with fy_col:
    fy = FiscalYear(st.selectbox("Period", [2025, 2024], format_func=lambda y: f"FY{y}" + (" (Jul–Dec)" if y == 2024 else "")))
tenant = get_tenant(session.tenant_id)
w = get_warehouse(session.tenant_id)
with head:
    mode = resolve_mode()
    live = model_reachable() and mode != "replay"
    st.markdown(
        f'<p class="hdr-name">{tenant.name}</p><p class="hdr-meta">{session.role.capitalize()} view · data as of '
        f'{w.as_of:%d %b %Y} · synthetic data</p>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------- funder role: the export only
if session.role == "funder":
    st.write("")
    st.markdown(":gray-badge[:material/lock: Funder access] You see the published report only. "
                "Counts from 1 to 4 are hidden, and so is any count that could be worked out from them.")
    report_html = render_html(session.tenant_id, fy.year)
    st.download_button("Download report", report_html, file_name=f"{session.tenant_id}_{fy.label}_funder_report.html",
                       mime="text/html")
    components.html(report_html, height=1500, scrolling=True)
    st.stop()

tab_today, tab_notes, tab_ask, tab_funder, tab_dq = st.tabs(
    ["Today", "Staff notes", "Ask a question", "Funder report", "Data quality"])
reviews = ReviewStore()
decisions = reviews.decisions(session.tenant_id)

# ---------------------------------------------------------------- today: status board
with tab_today:
    flags = board(w, decisions)
    with st.container(key="strip"):
        cols = st.columns(len(flags), gap="medium")
        for col, fl in zip(cols, flags):
            with col:
                value = fl.value.replace(" / ", '<span class="k-unit"> / ') + ("</span>" if " / " in fl.value else "")
                st.markdown(f'<div class="k-label">{fl.label}</div><div class="k-value">{value}</div>', unsafe_allow_html=True)
                st.markdown(f":{BADGE[fl.status]}-badge[:material/{STATUS_ICON[fl.status]}: {fl.badge}]")
                st.caption(fl.detail + (f"  \nNext: {fl.action}" if fl.action else ""))

    start, end = pd.Timestamp(fy.start), min(pd.Timestamp(fy.end), pd.Timestamp(w.as_of))
    census = w.nightly_census[(w.nightly_census["night"] >= start) & (w.nightly_census["night"] <= end)]
    occ = monthly_occupancy(w.nightly_census, fy)
    st.write("")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        section("Residents each night", f"{fy.label} · beds filled {occ.rate:.0%} of nights")
        st.altair_chart(census_chart(census), width="stretch")
    with c2:
        section("Admissions and discharges", f"{fy.label} · by month")
        st.altair_chart(flow_chart(w.residents, start, end), width="stretch")
    if fy.year == 2024:
        st.caption(":material/info: The file starts with July 2024 referrals. Anyone already in the house then is missing, "
                   "so early months may read low.")

    f = funnel(w.residents, fy, w.as_of)
    s = stays(w.residents, fy)
    o6, o12 = outcomes(w.followups, 6), outcomes(w.followups, 12)
    st.write("")
    section(f"{fy.label} at a glance")
    rows = [
        ("Referral to admission", f"{f.overall.rate:.0%}", f"{f.overall.n} of {f.overall.of} referrals with {MATURITY_DAYS}+ days to progress"),
        ("Beds filled", f"{occ.rate:.0%}", f"{occ.bed_nights:,} of {occ.capacity_nights:,} bed-nights"),
        ("Typical stay", f"{fmt_days(s.km_median_days)} days", f"{s.admitted_n} admitted, {s.ongoing.n} still in the house"),
        ("Engaged in recovery at 6 months", f"{o6.engaged_worst_case:.0%}–{o6.engaged_best_case:.0%}",
         f"{o6.due_n} due · {o6.engaged} confirmed · {o6.no_outcome} no known outcome · all years"),
        ("Engaged in recovery at 12 months", f"{o12.engaged_worst_case:.0%}–{o12.engaged_best_case:.0%}",
         f"{o12.due_n} due, mostly early leavers · too few to judge"),
    ]
    st.markdown(
        '<table class="glance"><thead><tr><th>Measure</th><th style="text-align:right">Value</th><th>Based on</th></tr></thead><tbody>'
        + "".join(f'<tr><td>{m}</td><td class="num">{v}</td><td class="base">{b}</td></tr>' for m, v, b in rows)
        + "</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption("Ranges run from worst case (nobody we couldn't reach is engaged) to best case (all of them are). "
               "Outcomes are never reported only among people we reached.")

    st.write("")
    with st.expander("Referrals: from referral to admission"):
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.altair_chart(funnel_chart(f.stages), width="stretch")
        with c2:
            st.dataframe(pd.DataFrame([{"Step": k, "People": v.n, "Median days": fmt_days(v.median),
                                        "90% within (days)": fmt_days(v.p90)} for k, v in f.timings.items()]),
                         hide_index=True, width="stretch")
            if f.cohort_n > f.matured_n:
                st.caption(f"{f.cohort_n - f.matured_n} people referred after {f.cutoff:%d %b %Y} are too recent to judge "
                           "and are not in these rates.")
        cohort = w.residents[(w.residents["referral_fy"] == fy.year) & ~w.residents["admitted"]]
        if len(cohort):
            section("Not admitted: what the staff notes say",
                    "Shown next to the recorded data, not instead of it. Not yet confirmed by staff.")
            t = (cohort.assign(state=cohort["note_referral_state"].fillna("no usable note"),
                               reason=cohort["note_referral"].fillna("no usable note").map(label),
                               when=cohort["matured"].map({True: "Had 60+ days", False: "Too recent"}))
                 .pivot_table(index=["state", "reason"], columns="when", values="resident_id", aggfunc="count", fill_value=0)
                 .reset_index().rename(columns={"state": "Open or closed", "reason": "Note says"}))
            st.dataframe(t, hide_index=True, width="stretch")
        st.markdown(
            f"""
- Everyone referred in {fy.label}, followed to the extract date. Referrals from the last {MATURITY_DAYS} days are
  kept out of the rates; {MATURITY_DAYS} days covers 90% of admissions.
- Admitted without an intake date: counted as having passed intake, left out of intake timings.
- Left out of timings: {", ".join(f"{n} from '{k.lower()}'" for k, n in f.timing_exclusions.items() if n) or "none"}.
"""
        )
    with st.expander("Occupancy by month"):
        st.altair_chart(occupancy_chart(occ.monthly), width="stretch")
        st.markdown(
            f"""
- Counted each night: a resident fills a bed from admission up to, not including, discharge.
- Missing discharge dates are estimated as admission + {w.meta['estimated_stay_days']:.0f} days (median early-leaver stay),
  for occupancy only: {occ.estimated_bed_nights} of {occ.bed_nights:,} bed-nights.
- Aftercare residents have left the house and do not fill a bed.
"""
        )
    with st.expander("Length of stay"):
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.dataframe(s.finished.rename(columns={"group": "Finished stays", "n": "People", "median_days": "Median days",
                                                    "p90_days": "90% within (days)"}).round(0), hide_index=True, width="stretch")
            st.caption(f"Still in the house: {s.ongoing.n} people, {fmt_days(s.ongoing.median)} days so far (median).")
        with c2:
            st.altair_chart(km_chart(s.km_curve), width="stretch")
        st.markdown(
            f"""
- People admitted in {fy.label}. Finished stays alone give {fmt_days(s.finished_all.median)} days, biased short
  because the longest stays are still going.
- Kaplan-Meier counts people still in the house as "at least this many days".
  {s.missing_discharge_date} people with no discharge date are left out.
"""
        )
    with st.expander("Outcomes after leaving"):
        st.markdown(legend_html(), unsafe_allow_html=True)
        c1, c2 = st.columns(2, gap="large")
        for col, r in ((c1, o6), (c2, o12)):
            with col:
                section(f"{r.horizon_months}-month follow-up", f"{r.due_n} people due")
                st.altair_chart(outcomes_chart(pd.DataFrame({"outcome": list(r.counts), "n": list(r.counts.values())}),
                                               legend=False), width="stretch")
        section("6 months: completed the program vs left early")
        by_group = o6.by_group.drop(columns="due").stack().rename("n").reset_index()
        st.altair_chart(outcomes_chart(by_group, "completion_group", legend=False), width="stretch")
        st.dataframe(pd.DataFrame([{OUTCOME_LABELS[k]: v for k, v in r.counts.items()} | {"Due": r.due_n,
                     "Not yet due": r.not_yet_due_n} for r in (o6, o12)], index=["6 months", "12 months"]), width="stretch")
        st.markdown(
            """
- Everyone who has left and whose follow-up date (from discharge) has passed, including people who left early.
- No known outcome has three parts, kept separate: lost to follow-up, unknown, and due but not recorded.
"""
        )

# ---------------------------------------------------------------- staff notes
with tab_notes:
    ran = bool(w.meta.get("notes_model_ran"))
    st.caption("Fields read from staff notes. Notes are redacted first; every value quotes the note it came from. "
               "Recorded data stays the source of truth until staff confirm. "
               + ("Read by rules and Claude." if ran else "Read by rules only: the model's answers aren't recorded yet, "
                  "so nothing is agreed and everything waits for review."))
    nf = w.note_findings
    queue = review_queue(w, decisions)
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        section(f"Review queue · {len(queue)}", "Risk flags first. Confirm what the note says, or reject it.")
        shown = queue.head(15)
        if shown.empty:
            st.markdown(":green-badge[:material/check_circle: Up to date] Nothing waiting for review.")
        for row in shown.itertuples():
            a, b, c = st.columns([4, 1.4, 1.3], vertical_alignment="center")
            tag = {"risk": ":orange-badge[:material/warning: risk]", "referral": ":gray-badge[referral]",
                   "discharge": ":gray-badge[discharge]", "engagement": ":gray-badge[engagement]"}[row.field]
            a.markdown(f"{tag} **{label(row.value)}** · {row.resident_id}  \n:gray[“{row.quote}” · found by {row.source}]")
            if b.button("Confirm", key=f"ok_{session.tenant_id}_{row.key}"):
                reviews.decide(session.tenant_id, row.resident_id, row.field, row.value, "confirm", session.user_id)
                st.rerun()
            if c.button("Reject", key=f"no_{session.tenant_id}_{row.key}"):
                reviews.decide(session.tenant_id, row.resident_id, row.field, row.value, "reject", session.user_id)
                st.rerun()
        if len(queue) > len(shown):
            st.caption(f"{len(queue) - len(shown)} more in the queue.")
    with c2:
        section("What the notes add")
        summary = (nf.assign(Field=nf["field"], Value=nf["value"].map(label))
                   .groupby(["Field", "Value"]).agg(People=("resident_id", "nunique")).reset_index())
        st.dataframe(summary, hide_index=True, width="stretch", height=420)
        st.caption(f"{len(decisions)} staff decisions recorded. Quotes rejected by the validator at the last build: "
                   f"{int(w.meta.get('notes_quotes_rejected', 0))}.")

# ---------------------------------------------------------------- ask
with tab_ask:
    agent = get_agent()
    turns_key = f"turns_{session.tenant_id}"
    st.session_state.setdefault(turns_key, [])
    turns: list[dict] = st.session_state[turns_key]

    st.caption("Totals only. The AI never sees resident records; every number comes from a checked, read-only query. "
               + ("Answered live by Claude." if live else "Replaying recorded answers (no API key set)."))
    ex = st.columns(4, gap="small")
    for i, q in enumerate(EXAMPLES):
        if ex[i].button(q, key=f"ex_{i}", width="stretch"):
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
                    st.caption(f":material/bookmark: Using {tenant.name}'s definition of '{d.term}': {d.label} "
                               f"(version {d.version}, set by {d.defined_by}).")
                for c in r.caveats:
                    st.caption(c)
                with st.expander("Data, spec and query"):
                    st.dataframe(r.frame, hide_index=True, width="stretch")
                    st.json(r.executed.model_dump(mode="json"), expanded=False)
                    st.code(r.sql, language="sql")
                    st.caption(f"Parameters {r.params} · spec {r.executed.hash} · audit {r.event_id} · "
                               f"model: {r.llm_mode} · {r.elapsed_ms} ms")
            elif isinstance(r, Clarification):
                st.markdown(f":orange-badge[:material/help: Needs a definition] **{r.question}**")
                st.markdown(r.why)
                if turn.get("answered"):
                    st.caption(f"You chose: {turn['answered']}")
                else:
                    for c in r.choices:
                        if st.button(c.label, key=f"choice_{session.tenant_id}_{idx}_{c.id}"):
                            agent.define(session, r.term, c.id)
                            turn["answered"] = c.label
                            turns.append({"question": turn["question"], "result": agent.ask(turn["question"], session)})
                            st.rerun()
                    st.caption(f"Saved as {tenant.name}'s definition and shown under every answer that uses it.")
            else:
                st.markdown(f":gray-badge[:material/block: Not answered] {r.message}")
                st.caption(f"Audit {r.event_id}")

    for i, t in enumerate(turns):
        render(t, i)

    with st.expander(f"{tenant.name} definitions"):
        current = DefinitionStore().current(session.tenant_id)
        if not current:
            st.caption("None yet. The first time a question uses a word like 'sober' or 'active', you'll be asked what it means.")
        for term, d in sorted(current.items()):
            a, b = st.columns([6, 1], vertical_alignment="center")
            a.markdown(f"**{term}**: {d.label}  \n:gray[version {d.version}, set by {d.defined_by}, {d.defined_at}]")
            if b.button("Reset", key=f"reset_{session.tenant_id}_{term}"):
                DefinitionStore().save(session.tenant_id, term, None, session.user_id)
                st.rerun()
        st.caption("Words that always need a definition: " + ", ".join(sorted(GLOSSARY)) + ".")

    q = st.chat_input("Ask about your house")
    if q:
        turns.append({"question": q, "result": agent.ask(q, session)})
        st.rerun()

# ---------------------------------------------------------------- funder report preview
with tab_funder:
    st.caption("What leaves the house. Counts from 1 to 4 are hidden, and so is any count that could be worked out from them.")
    report_html = render_html(session.tenant_id, fy.year)
    st.download_button("Download report", report_html, file_name=f"{session.tenant_id}_{fy.label}_funder_report.html",
                       mime="text/html")
    components.html(report_html, height=1500, scrolling=True)

# ---------------------------------------------------------------- data quality
with tab_dq:
    st.caption("Every record that breaks a rule, and what the metrics do about it. Directors only: this page lists resident IDs.")
    dq = w.dq_issues
    st.dataframe(dq.groupby(["rule", "treatment"]).size().rename("records").reset_index(), hide_index=True, width="stretch")
    st.dataframe(dq, hide_index=True, width="stretch")
