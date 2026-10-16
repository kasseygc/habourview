"""Funder report: one self-contained HTML file, small counts hidden (D-08), printable to PDF.

The director's dashboard shows exact counts. This export is what leaves the house.
"""

from __future__ import annotations

import base64
import html
from datetime import date
from pathlib import Path

import pandas as pd
import vl_convert as vlc

from axon.charts import occupancy_chart
from axon.config import OUT_DIR, SMALL_CELL_THRESHOLD, FiscalYear
from axon.metrics.funnel import funnel
from axon.metrics.occupancy import monthly_occupancy
from axon.metrics.outcomes import OUTCOME_LABELS, outcomes
from axon.metrics.stays import stays
from axon.suppress import is_small, rate_is_publishable, suppress_counts, suppress_total
from axon.tenants import get_tenant
from axon.warehouse import Warehouse, load

HIDDEN = "—"


def _pct(n: int, d: int) -> str:
    return f"{n / d:.0%}" if rate_is_publishable(n, d) else HIDDEN


def _days(v: float | None, n: int) -> str:
    return HIDDEN if v is None or is_small(n) else f"{v:.0f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_sections(w: Warehouse, fy: FiscalYear) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    as_of: date = w.as_of
    partial = " (July to December only: the data starts in July 2024)" if fy.year == 2024 else ""

    f = funnel(w.residents, fy, as_of)
    rows = [[s.stage, suppress_total(s.n), "" if i == 0 else _pct(s.n, s.of)] for i, s in enumerate(f.stages)]
    rows.append(["Referral to admission, overall", "", _pct(f.overall.n, f.overall.of)])
    recent = int(f.recent["n"].sum())
    sections.append((
        "Referrals and admissions",
        f"<p>People referred in {fy.label}{partial} who had at least 60 days to move forward "
        f"(referred by {f.cutoff:%d %b %Y}). The {suppress_total(recent)} referrals after that date are too recent to judge "
        f"and are not in these rates.</p>"
        + _table(["Stage", "People", "Moved on from previous stage"], rows),
    ))

    o = monthly_occupancy(w.nightly_census, fy)
    svg = vlc.vegalite_to_svg(occupancy_chart(o.monthly).properties(width=620).to_dict())
    rows = [[m.month.strftime("%b %Y") + (" (partial)" if m.partial_month else ""), f"{m.occupancy_rate:.0%}",
             f"{m.avg_residents:.1f} of {m.beds}"] for m in o.monthly.itertuples()]
    sections.append((
        "Bed occupancy",
        f"<p>Across {fy.label}{partial}, beds were <strong>{o.rate:.0%}</strong> full, counted each night "
        f"(a resident fills a bed from admission up to, not including, discharge).</p>"
        f'<div class="chart">{svg}</div>' + _table(["Month", "Beds filled", "Average residents a night"], rows),
    ))

    cohort = w.residents[w.residents["admitted"] & (w.residents["admission_fy"] == fy.year)]
    # Funder figures use recorded reasons only: anything filled in from notes stays "other or unknown".
    exit_type = cohort["exit_type"].where(~cohort["exit_from_notes"].astype(bool), "other_or_unknown")
    names = {"completed": "Completed the program", "left_by_choice": "Left by choice",
             "discharged_by_house": "Discharged by the house", "transferred": "Transferred",
             "custody": "Custody", "other_or_unknown": "Other or not recorded", "still_in_program": "Still in the program"}
    counts = {names[k]: int((exit_type == k).sum()) for k in names}
    shown = suppress_counts(counts)
    total = len(cohort)
    done = counts[names["completed"]]
    sections.append((
        "How stays ended",
        f"<p>Everyone admitted in {fy.label}{partial} ({suppress_total(total)} people). Completion is counted separately "
        f"from discharge: <strong>{_pct(done, total)}</strong> completed the program.</p>"
        + _table(["How the stay ended", "People"], [[k, v] for k, v in shown.items()] + [["Everyone admitted", suppress_total(total)]]),
    ))

    s = stays(w.residents, fy)
    rows = [[r.group.strip(), suppress_total(int(r.n)), _days(r.median_days, int(r.n))]
            for r in s.finished.itertuples() if not r.group.startswith("  ")]
    rows.append(["Still in the house at the extract date (days so far)", suppress_total(s.ongoing.n),
                 _days(s.ongoing.median, s.ongoing.n)])
    km = HIDDEN if s.km_median_days is None else f"{s.km_median_days:.0f}"
    sections.append((
        "Length of stay",
        f"<p>People admitted in {fy.label}. Typical stay, counting people still in the house: "
        f"<strong>{km} days</strong> (Kaplan-Meier median).</p>"
        + _table(["Group", "People", "Median days"], rows),
    ))

    for h in (6, 12):
        r = outcomes(w.followups, h)
        shown = suppress_counts({OUTCOME_LABELS[k]: v for k, v in r.counts.items()})
        rows = [[k, v] for k, v in shown.items()] + [["Everyone due", suppress_total(r.due_n)]]
        if rate_is_publishable(r.engaged, r.due_n) and rate_is_publishable(r.engaged + r.no_outcome, r.due_n):
            headline = (f"<strong>{_pct(r.engaged, r.due_n)}</strong> confirmed engaged in recovery (worst case); "
                        f"<strong>{_pct(r.engaged + r.no_outcome, r.due_n)}</strong> if everyone we could not reach is engaged (best case).")
        else:
            headline = "Too few people for a published rate."
        span = "" if r.first_discharge is None else f" (left the house {r.first_discharge:%b %Y} to {r.last_discharge:%b %Y})"
        sections.append((
            f"{h}-month follow-up",
            f"<p>Everyone whose {h}-month follow-up date has passed{span}, including people who left early. "
            f"Nobody is left out for being hard to reach. {headline}</p>"
            + _table(["Outcome", "People"], rows),
        ))

    sections.append((
        "How we count",
        "<ul>"
        f"<li>Data as of {as_of:%d %B %Y}. Fiscal years run January to December.</li>"
        f"<li>Counts from 1 to {SMALL_CELL_THRESHOLD - 1} are shown as '&lt;{SMALL_CELL_THRESHOLD}'. "
        f"Where one hidden count could be worked out from a total, another is hidden too ({HIDDEN}). "
        "Rates are hidden when they would reveal a small count.</li>"
        "<li>'Engaged in recovery' is what follow-up calls record. We do not report a 'sobriety' rate.</li>"
        "<li>We never report outcomes only among people we reached; that would overstate results.</li>"
        "<li>Every figure here comes from recorded fields. Details read from staff notes with AI assistance are "
        "not included until staff confirm them.</li>"
        "</ul>",
    ))
    return sections


FONT_PATH = Path(__file__).resolve().parents[3] / "app" / "static" / "fonts" / "InterVariable.woff2"

CSS = """
:root{--bg:#ffffff;--frost:#f7f5fb;--line:#eceaf2;--line2:#d7d5e0;--ink:#030302;--ink2:#54586b;--sage:#446a3f}
body{font-family:Inter,system-ui,sans-serif;color:var(--ink);background:var(--bg);max-width:760px;
  margin:3rem auto;padding:0 20px;line-height:1.7;font-size:15px;font-variant-numeric:tabular-nums}
h1{font-size:1.45rem;font-weight:600;margin:0 0 .4rem;line-height:1.3}
h2{font-size:.78rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--sage);margin:2.6rem 0 .6rem;
  padding-bottom:.45rem;border-bottom:1px solid var(--line)}
p{margin:.6rem 0 1rem} ul{padding-left:1.2rem} li{margin-bottom:.55rem}
.sub{color:var(--ink2);margin:0 0 2rem}
table{border-collapse:collapse;width:100%;margin:1rem 0 1.5rem}
th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid var(--line)}
th{color:#7e7d91;font-weight:500;font-size:.78rem;letter-spacing:.05em;text-transform:uppercase}
td:not(:first-child),th:not(:first-child){text-align:right}
.chart{margin:1.25rem 0} .chart svg{max-width:100%;height:auto}
strong{font-weight:600}
.note{font-size:.85rem;color:var(--ink2);background:var(--frost);border-radius:8px;padding:.6rem .8rem}
@media print{body{margin:0;max-width:none}}
"""


def _font_face() -> str:
    """Embed Inter so the file stays self-contained and never calls out to a font server."""
    if not FONT_PATH.exists():
        return ""
    data = base64.b64encode(FONT_PATH.read_bytes()).decode()
    return f"@font-face{{font-family:Inter;src:url(data:font/woff2;base64,{data}) format('woff2');font-weight:100 900}}"


def render_html(tenant_id: str, fy_year: int) -> str:
    tenant = get_tenant(tenant_id)
    w = load(tenant)
    fy = FiscalYear(fy_year)
    body = "".join(f"<h2>{html.escape(t)}</h2>{content}" for t, content in build_sections(w, fy))
    title = f"{tenant.name}: {fy.label} report for funders"
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_font_face()}{CSS}</style></head><body>"
        f"<h1>{html.escape(title)}</h1><p class='sub'>Fictional house, synthetic data. Data as of {w.as_of:%d %B %Y}.</p>"
        f"{body}</body></html>"
    )


def write_report(tenant_id: str, fy_year: int) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{tenant_id}_FY{fy_year}_funder_report.html"
    path.write_text(render_html(tenant_id, fy_year))
    return path
