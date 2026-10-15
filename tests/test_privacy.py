"""PHI handling: redaction, small-cell suppression, and what leaves the house."""

from __future__ import annotations

import re

import duckdb
import pandas as pd
import pytest

from axon.redact import redact
from axon.report.funder import render_html
from axon.suppress import rate_is_publishable, suppress_counts
from axon.tenants import get_tenant

PLANTED = {
    "HV-0035": "Res. asked staff to update emerg contact to brother [NAME] [PHONE].",
    "HV-0072": "Spoke w/ probation officer [NAME] re: conditions.",
    "HV-0149": "Sister [NAME] dropped off clothes; res in good spirits.",
    "HV-0158": "Mom ([NAME]) called asking about visiting hrs, call back [PHONE].",
}


@pytest.fixture(scope="module")
def notes():
    df = pd.read_csv(get_tenant("harbourview").csv_path, dtype=str, keep_default_na=False)
    return dict(zip(df["resident_id"], df["staff_note"].str.strip()))


@pytest.mark.parametrize("rid, expected", PLANTED.items())
def test_planted_phi_is_redacted(notes, rid, expected):
    assert redact(notes[rid]).text == expected


def test_ordinary_notes_are_left_alone(notes):
    changed = {rid for rid, n in notes.items() if redact(n).changed}
    assert changed == set(PLANTED)


@pytest.mark.parametrize("q, expected", [
    ("How is HV-0035 doing?", "How is [RESIDENT_ID] doing?"),
    ("Did Kevin's brother call 905 555 0187?", "Did [NAME]'s brother call [PHONE]?"),
    ("admissions since 2025-03-01", "admissions since 2025-03-01"),
    ("health card 1234-567-890-AB", "health card [HEALTH_CARD]"),
])
def test_questions_are_redacted_but_keep_dates(q, expected):
    assert redact(q, keep_dates=True).text == expected


def test_only_types_are_reported_never_values():
    r = redact("brother Kevin 905-555-0187")
    assert sorted(r.found) == ["NAME", "PHONE"]
    assert "Kevin" not in str(r.found)


def test_small_counts_hidden_with_complementary_cell():
    shown = suppress_counts({"a": 20, "b": 3, "c": 9, "d": 0})
    assert shown == {"a": "20", "b": "<5", "c": "hidden", "d": "0"}


def test_two_small_cells_need_no_extra_suppression():
    assert suppress_counts({"a": 20, "b": 3, "c": 4}) == {"a": "20", "b": "<5", "c": "<5"}


@pytest.mark.parametrize("num, den, ok", [(21, 51, True), (1, 11, False), (47, 51, False), (3, 4, False)])
def test_rates_that_reveal_small_counts_are_hidden(num, den, ok):
    assert rate_is_publishable(num, den) is ok


def test_funder_report_has_no_small_counts_or_identifiers():
    html = render_html("harbourview", 2025)
    cells = re.findall(r"<td>(\d+)</td>", html)
    assert cells and all(not (0 < int(c) < 5) for c in cells)
    assert not re.search(r"\bHV-\d{4}\b", html)
    assert "&lt;5" in html  # 12-month cells are hidden


def test_staff_notes_never_reach_the_warehouse():
    con = duckdb.connect(str(get_tenant("harbourview").warehouse_path), read_only=True)
    cols = {r[0] for t in ("residents", "followups", "nightly_census")
            for r in con.execute(f"DESCRIBE {t}").fetchall()}
    con.close()
    assert "staff_note" not in cols
