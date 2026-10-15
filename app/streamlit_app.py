"""Harbourview analytics: director dashboard, natural-language questions, funder export.

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
from axon.agent.llm import has_api_credentials, resolve_mode  # noqa: E402
from axon.agent.pipeline import Agent, Answer, Clarification, Session  # noqa: E402
from axon.charts import agent_chart, funnel_chart, km_chart, occupancy_chart, outcomes_chart  # noqa: E402
from axon.config import MATURITY_DAYS, FiscalYear  # noqa: E402
from axon.metrics.funnel import funnel  # noqa: E402
from axon.metrics.occupancy import monthly_occupancy  # noqa: E402
from axon.metrics.outcomes import OUTCOME_LABELS, outcomes  # noqa: E402
from axon.metrics.stays import stays  # noqa: E402
from axon.report.funder import render_html  # noqa: E402
from axon.tenants import TENANTS, get_tenant  # noqa: E402
from axon.warehouse import build_all, load  # noqa: E402

st.set_page_config(page_title="Harbourview analytics", page_icon=":bar_chart:", layout="wide")

EXAMPLES = [
    "How many admissions did we have each month in 2025?",
    "How full was the house each month in 2025?",
    "What percentage of residents were sober at 6 months?",
    "How many active residents do we have, by phase?",
]
SIGN_INS = {
    "Director, Harbourview House": Session("harbourview", "director@harbourview"),
    "Director, Northshore Youth Residence": Session("northshore", "director@northshore"),
}


@st.cache_resource
def get_agent() -> Agent:
    return Agent()


@st.cache_resource
def ensure_built() -> bool:
    missing = [t for t in TENANTS.values() if t.csv_path.exists() and not t.warehouse_path.exists()]
    if missing:
        build_all()
    return True


@st.cache_data
def get_warehouse(tenant_id: str):
    return load(get_tenant(tenant_id))


def fmt_days(v: float | None) -> str:
    return "–" if v is None or pd.isna(v) else f"{v:.0f}"


# ---------------------------------------------------------------- sidebar
ensure_built()
with st.sidebar:
    who = st.selectbox("Signed in as (demo)", list(SIGN_INS))
    session = SIGN_INS[who]
    st.caption("Demo only. In production the house comes from your login. Nothing you type can change it.")
    fy_year = st.radio("Fiscal year (Jan to Dec)", [2025, 2024], format_func=lambda y: f"FY{y}" + (" (Jul to Dec only)" if y == 2024 else ""))
    fy = FiscalYear(fy_year)
    w = get_warehouse(session.tenant_id)
    st.caption(f"Data as of {w.as_of:%d %b %Y}. Synthetic data, fictional houses.")
    mode = resolve_mode()
    if has_api_credentials() and mode != "replay":
        st.caption("Questions: answered live by Claude (new ones are recorded).")
    else:
        st.caption("Questions: replaying recorded answers (no API key set). New wording will not work offline.")

tenant = get_tenant(session.tenant_id)
st.title(tenant.name)
tab_dash, tab_ask, tab_funder, tab_dq = st.tabs(["Dashboard", "Ask a question", "Funder report", "Data quality"])

# ---------------------------------------------------------------- dashboard
with tab_dash:
    f = funnel(w.residents, fy, w.as_of)
    occ = monthly_occupancy(w.nightly_census, fy)
    s = stays(w.residents, fy)
    o6, o12 = outcomes(w.followups, 6), outcomes(w.followups, 12)
    in_house = int(w.residents["in_residence"].sum())

    st.caption(f"{fy.label}{' (July to December only: the data starts in July 2024)' if fy.year == 2024 else ''} · "
               f"data as of {w.as_of:%d %B %Y}")
    k = st.columns(5)
    k[0].metric("Referrals", f.cohort_n, help="Everyone referred in this fiscal year.")
    k[1].metric("Referral to admission", f"{f.overall.rate:.0%}", help=f"{f.overall.n} of {f.overall.of} referrals that had {MATURITY_DAYS}+ days to progress.")
    k[2].metric("Beds filled", f"{occ.rate:.0%}", help="Bed-nights used / (beds x nights) across the fiscal year.")
    k[3].metric("In the house now", f"{in_house} of {w.capacity}", help="Phases 1 to 3 on the extract date.")
    k[4].metric("6-month follow-ups due", o6.due_n, help="Everyone whose 6-month date has passed, across all years.")

    st.subheader("Referral to intake to admission")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.altair_chart(funnel_chart(f.stages), width="stretch")
        st.caption(f"Referrals made by {f.cutoff:%d %b %Y} ({f.matured_n} people), so each had at least {MATURITY_DAYS} days to move forward. "
                   f"Overall, {f.overall.n} of {f.overall.of} ({f.overall.rate:.0%}) were admitted.")
    with c2:
        timing = pd.DataFrame(
            [{"Step": k_, "People": v.n, "Median days": fmt_days(v.median), "90% within (days)": fmt_days(v.p90)}
             for k_, v in f.timings.items()]
        )
        st.dataframe(timing, hide_index=True, width="stretch")
        st.caption("Timings count only people who reached the next step. "
                   + ", ".join(f"{n} left out of '{k_.lower()}' (dates out of order or missing)" for k_, n in f.timing_exclusions.items() if n) + ".")
        if f.cohort_n > f.matured_n:
            st.markdown(f"**Too recent to judge:** {f.cohort_n - f.matured_n} referrals after {f.cutoff:%d %b %Y}")
            st.dataframe(f.recent.rename(columns={"stage": "Where they are now", "n": "People",
                                                  "median_days_since_referral": "Median days since referral"}),
                         hide_index=True, width="stretch")
    with st.expander("How this is calculated"):
        st.markdown(
            f"- **Cohort:** everyone referred in {fy.label}, followed forward to the extract date.\n"
            f"- **Still in progress:** referrals made in the last {MATURITY_DAYS} days before the extract date are left out of the "
            f"rates and shown separately. {MATURITY_DAYS} days covers 90% of admissions (90th percentile, referral to admission: 41 days).\n"
            "- **Admitted without an intake date** counts as having passed intake (they were assessed somehow), "
            "but is left out of intake timings.\n"
            "- **Median and '90% within'** use linear interpolation, the same as the database's quantile function."
        )

    st.subheader("Bed occupancy")
    st.altair_chart(occupancy_chart(occ.monthly), width="stretch")
    st.caption(f"{occ.rate:.0%} of bed-nights filled in {fy.label} ({w.capacity} beds). Dashed line: every bed full. "
               + (f"{occ.estimated_bed_nights} bed-nights come from estimated discharge dates." if occ.estimated_bed_nights else ""))
    if fy.year == 2024 or occ.monthly["month"].min() < pd.Timestamp("2025-04-01"):
        st.caption("Early months: the file starts with referrals from July 2024. If anyone was already living in the house "
                   "before then, they are missing, and occupancy before about April 2025 is understated.")
    with st.expander("How this is calculated"):
        st.markdown(
            "- **Midnight count:** a resident fills a bed every night from admission up to, but not including, discharge.\n"
            "- **Monthly occupancy** = bed-nights used / (beds x nights in the month). Shown with the average residents a "
            "night and the busiest night.\n"
            f"- **Missing discharge dates** ({int(w.residents['discharge_date_estimated'].sum())} people) are estimated as admission + "
            f"{w.meta['estimated_stay_days']:.0f} days (the median early-leaver stay), for occupancy only.\n"
            "- **Aftercare** residents have left the house and do not fill a bed."
        )
        st.dataframe(occ.monthly.assign(month=occ.monthly["month"].dt.strftime("%b %Y"))[
            ["month", "occupancy_rate", "avg_residents", "peak_residents", "beds", "nights"]].round(3),
            hide_index=True, width="stretch")

    st.subheader("Length of stay")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.metric("Typical stay, counting people still here", f"{fmt_days(s.km_median_days)} days",
                  help="Kaplan-Meier median: people still in the house count as 'at least this long'.")
        tbl = s.finished.rename(columns={"group": "Finished stays", "n": "People", "median_days": "Median days", "p90_days": "90% within (days)"})
        st.dataframe(tbl.round(0), hide_index=True, width="stretch")
        st.markdown(f"**Still in the house:** {s.ongoing.n} people, {fmt_days(s.ongoing.median)} days so far (median), "
                    f"longest {fmt_days(s.ongoing_max)}.")
    with c2:
        st.altair_chart(km_chart(s.km_curve), width="stretch")
        st.caption(f"People admitted in {fy.label} (n={s.admitted_n}). The line shows the share still in the house after each day.")
    with st.expander("How this is calculated"):
        st.markdown(
            f"- **Cohort:** people admitted in {fy.label}.\n"
            f"- **Finished stays** use recorded discharge dates. The median of finished stays alone ({fmt_days(s.finished_all.median)} days) "
            "is biased short, because the longest stays are the ones still going.\n"
            "- **Kaplan-Meier** counts people still in the house as 'at least this many days' instead of dropping them.\n"
            f"- **No discharge date:** {s.missing_discharge_date} people are left out (their stay length is unknown)."
        )

    st.subheader("Outcomes after leaving")
    c1, c2 = st.columns(2)
    for col, r in ((c1, o6), (c2, o12)):
        with col:
            st.markdown(f"**{r.horizon_months}-month follow-up** · {r.due_n} people due")
            counts = pd.DataFrame({"outcome": list(r.counts), "n": list(r.counts.values())})
            st.altair_chart(outcomes_chart(counts), width="stretch")
            st.markdown(f"Confirmed engaged in recovery: **{r.engaged_worst_case:.0%}** ({r.engaged} of {r.due_n}). "
                        f"Range: **{r.engaged_worst_case:.0%}** (worst case: nobody unreached is engaged) to "
                        f"**{r.engaged_best_case:.0%}** (best case: everyone unreached is).")
            if r.due_n < 20:
                st.caption(f"Only {r.due_n} people so far, mostly early leavers. Too few to judge.")
    by_group = o6.by_group.drop(columns="due").stack().rename("n").reset_index()
    st.markdown("**6-month outcomes: completed the program vs left early**")
    st.altair_chart(outcomes_chart(by_group, "completion_group"), width="stretch")
    with st.expander("How this is calculated"):
        st.markdown(
            "- **Who is counted:** everyone who has left the house and whose 6- or 12-month date (from discharge) has passed, "
            "**including people who left early**. Nobody is dropped for being hard to reach.\n"
            "- **No known outcome** has three parts, kept separate: lost to follow-up (tried, couldn't reach), unknown, and "
            "due but not recorded (a data-entry gap).\n"
            "- **Worst case** = confirmed engaged / everyone due. **Best case** assumes everyone without an outcome is engaged.\n"
            "- We do not show 'engaged among people we reached': it hides everyone we lost touch with."
        )
        st.dataframe(pd.DataFrame([{OUTCOME_LABELS[k_]: v for k_, v in r.counts.items()} | {"Due": r.due_n,
                     "Not yet due": r.not_yet_due_n} for r in (o6, o12)], index=["6 months", "12 months"]), width="stretch")

# ---------------------------------------------------------------- ask
with tab_ask:
    agent = get_agent()
    turns_key = f"turns_{session.tenant_id}"
    st.session_state.setdefault(turns_key, [])
    turns: list[dict] = st.session_state[turns_key]

    st.markdown("Ask about referrals, intakes, admissions, discharges, occupancy, follow-up outcomes or current residents. "
                "Answers are totals only; the AI never sees resident records, and every number comes from a checked query.")
    ex = st.columns(len(EXAMPLES))
    for i, q in enumerate(EXAMPLES):
        if ex[i].button(q, key=f"ex_{i}", width="stretch"):
            turns.append({"question": q, "result": agent.ask(q, session)})

    def render(turn: dict, idx: int) -> None:
        r = turn["result"]
        with st.chat_message("user"):
            st.markdown(turn["question"])
        with st.chat_message("assistant"):
            if isinstance(r, Answer):
                st.markdown(r.text)
                chart = agent_chart(r.spec, r.frame)
                if chart is not None:
                    st.altair_chart(chart, width="stretch")
                for d in r.definitions:
                    st.caption(f"Using {tenant.name}'s definition of '{d.term}': {d.label} "
                               f"(version {d.version}, set by {d.defined_by}).")
                for c in r.caveats:
                    st.caption(c)
                with st.expander("Data, spec and query"):
                    st.dataframe(r.frame, hide_index=True, width="stretch")
                    st.json(r.executed.model_dump(mode="json"), expanded=False)
                    st.code(r.sql, language="sql")
                    st.caption(f"Parameters: {r.params} · spec {r.executed.hash} · audit event {r.event_id} · "
                               f"model answer: {r.llm_mode} · query {r.elapsed_ms} ms")
            elif isinstance(r, Clarification):
                st.markdown(f"**{r.question}** {r.why}")
                if turn.get("answered"):
                    st.caption(f"You chose: {turn['answered']}")
                else:
                    for c in r.choices:
                        if st.button(c.label, key=f"choice_{session.tenant_id}_{idx}_{c.id}"):
                            agent.define(session, r.term, c.id)
                            turn["answered"] = c.label
                            turns.append({"question": turn["question"], "result": agent.ask(turn["question"], session)})
                            st.rerun()
                    st.caption(f"Your choice is saved as {tenant.name}'s definition and shown under every answer that uses it.")
            else:
                st.markdown(r.message)
                st.caption(f"Audit event {r.event_id}")

    for i, t in enumerate(turns):
        render(t, i)

    with st.expander(f"{tenant.name} definitions"):
        current = DefinitionStore().current(session.tenant_id)
        if not current:
            st.caption("None yet. The first time a question uses a word like 'sober' or 'active', you'll be asked what it means.")
        for term, d in sorted(current.items()):
            a, b = st.columns([5, 1])
            a.markdown(f"**{term}**: {d.label}  \n<small>version {d.version}, set by {d.defined_by}, {d.defined_at}</small>",
                       unsafe_allow_html=True)
            if b.button("Reset", key=f"reset_{session.tenant_id}_{term}"):
                DefinitionStore().save(session.tenant_id, term, None, session.user_id)
                st.rerun()
        st.caption("Known words that always need a definition: " + ", ".join(sorted(GLOSSARY)) + ".")

    q = st.chat_input("Ask a question about your house")
    if q:
        turns.append({"question": q, "result": agent.ask(q, session)})
        st.rerun()

# ---------------------------------------------------------------- funder report
with tab_funder:
    st.markdown("What leaves the house. Counts from 1 to 4 are hidden, and so is any count that could be worked out from them. "
                "Download it, then print to PDF if needed.")
    report_html = render_html(session.tenant_id, fy.year)
    st.download_button("Download funder report (HTML)", report_html, file_name=f"{session.tenant_id}_{fy.label}_funder_report.html",
                       mime="text/html")
    components.html(report_html, height=1400, scrolling=True)

# ---------------------------------------------------------------- data quality
with tab_dq:
    st.markdown("Every record that breaks a rule, and what the metrics do about it. Internal only: it lists resident IDs.")
    dq = w.dq_issues
    st.dataframe(dq.groupby(["rule", "treatment"]).size().rename("records").reset_index(), hide_index=True, width="stretch")
    st.dataframe(dq, hide_index=True, width="stretch")
