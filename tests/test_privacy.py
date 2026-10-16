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


def test_the_app_never_writes_what_users_type_to_disk(tmp_path, monkeypatch):
    from axon.agent import llm as llm_mod

    model = llm_mod.SpecModel(mode="auto", cassette_dir=tmp_path, save_recordings=False)
    monkeypatch.setattr(llm_mod, "model_reachable", lambda provider="ollama": True)
    monkeypatch.setattr(model, "_call_ollama", lambda system, user, schema: llm_mod.LLMCall("{}", "stub", "model", "stop"))
    model.complete([{"type": "text", "text": "instructions"}], "a question someone typed", {})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("text, expected", [
    ("Called Kevin, no answer.", "Called [NAME], no answer."),
    ("Spoke w/ Linda re: visit on Sunday.", "Spoke w/ [NAME] re: visit on Sunday."),
    ("Linda (sister) called twice today.", "[NAME] (sister) called twice today."),
    ("PO Martel requested an update on curfew.", "PO [NAME] requested an update on curfew."),
    ("Res tearful after call with Mom, Debbie.", "Res tearful after call with Mom, [NAME]."),
    ("Emergency contact changed to Sarah Thompson.", "Emergency contact changed to [NAME]."),
])
def test_names_with_no_relationship_word_are_redacted(text, expected):
    assert redact(text, directory=get_tenant("harbourview").directory()).text == expected


@pytest.mark.parametrize("text", ["Attending NA 3x/wk, AA on Sundays.", "SMART Recovery group Tuesday evening.",
                                  "Will follow up next week.", "Referred by CAMH, intake booked for Monday."])
def test_words_notes_need_are_not_mistaken_for_names(text):
    assert redact(text).text == text


def test_a_name_in_a_question_is_declined_before_the_model(make_agent):
    from axon.agent.pipeline import Declined, Session

    agent, stub = make_agent({})
    r = agent.ask("How is Tyler doing since he moved to phase 2?", Session("harbourview", "director@harbourview"))
    assert isinstance(r, Declined) and r.reason == "row_level"
    assert stub.calls == []


def test_name_redaction_holds_on_the_labelled_set():
    from axon.redaction_eval import run

    full = next(s for s in run(["en_core_web_lg"]) if s.name == "Rules + directory + detector (en_core_web_lg)")
    assert full.recall >= 0.95 and not full.keep_lost and not full.false_sentences
