"""Staff-note extraction: rules, the validator, the review policy, redaction before the model."""

from __future__ import annotations

import json

import pytest

from axon.agent.llm import LLMCall
from axon.notes import rules
from axon.notes.evaluate import load_gold
from axon.notes.extract import run_notes
from axon.notes.model import validate
from axon.notes.review import ReviewStore
from axon.status import board, review_queue
from axon.warehouse import AGENT_TABLES
from tests.conftest import make_raw


class NotesStub:
    """Answers a notes batch from a dict of {note substring: findings}."""

    def __init__(self, answers: dict[str, list[dict]], unclear: set[str] = frozenset()):
        self.answers, self.unclear, self.seen = answers, unclear, []

    def complete(self, system, user_text, schema):
        items = json.loads(user_text)
        self.seen += [i["note"] for i in items]
        notes = []
        for i in items:
            found = next((v for k, v in self.answers.items() if k in i["note"]), [])
            notes.append({"id": i["id"], "findings": found, "unclear": any(u in i["note"] for u in self.unclear)})
        return LLMCall(json.dumps({"notes": notes}), "stub", "stub", "end_turn")


def test_rules_match_every_labelled_note_from_the_file():
    for case in load_gold():
        if case["set"] == "file":
            got = {(f.field, f.value) for f in rules.extract(case["note"], case["status"])}
            assert got == case["expect"], case["note"]


def test_rules_respect_negation():
    assert rules.extract("Denies cravings, mood stable.", "phase_2") == []


def test_fields_depend_on_where_the_person_is():
    # A discharge-style note on someone never admitted yields nothing.
    assert rules.extract("left AMA", "not_admitted") == []
    assert [f.value for f in rules.extract("left AMA", "discharged")] == ["self_discharge"]


@pytest.mark.parametrize("finding, problem", [
    ({"field": "referral", "value": "declined", "quote": "client refused everything"}, "quote is not in the note"),
    ({"field": "risk", "value": "low_mood", "quote": "declined assessment"}, "field does not apply to this person"),
    ({"field": "referral", "value": "low_mood", "quote": "declined assessment"}, "value does not belong to the field"),
])
def test_validator_rejects_invented_or_misplaced_findings(finding, problem):
    item = {"id": "n1", "status": "not_admitted", "note": "Client declined assessment - wants outpatient instead"}
    ok, bad = validate(item, [finding])
    assert ok == [] and bad[0]["problem"] == problem


def _raw():
    return make_raw([
        dict(referral_date="2025-12-01", staff_note="Called x3, mailbox full. Mom (Linda) at 613-555-0142."),
        dict(referral_date="2025-12-02", staff_note="Phone disconnected. Closed referral."),
        dict(referral_date="2025-01-01", admission_date="2025-01-05", current_status="phase_1",
             staff_note="Res. settling in, attending all groups. Some cravings reported."),
    ])


def test_notes_are_redacted_before_the_model_sees_them():
    stub = NotesStub({})
    run_notes(_raw(), stub)
    joined = " ".join(stub.seen)
    assert "Linda" not in joined and "613-555" not in joined and "[PHONE]" in joined


def test_review_policy():
    stub = NotesStub({
        "Called x3": [{"field": "referral", "value": "unreachable", "quote": "Called x3, mailbox full"}],
        "Phone disconnected": [{"field": "referral", "value": "unreachable", "quote": "Phone disconnected"}],
        "settling in": [{"field": "risk", "value": "cravings", "quote": "Some cravings reported"},
                        {"field": "engagement", "value": "attending_groups", "quote": "attending all groups"}],
    })
    r = run_notes(_raw(), stub)
    review = {(x.resident_id, x.field, x.value): (x.review, x.source) for x in r.findings.itertuples()}
    assert review[("T-0001", "referral", "unreachable")] == ("needs_review", "model")      # model only
    assert review[("T-0002", "referral", "unreachable")] == ("agreed", "model+rules")      # both agree
    assert review[("T-0003", "risk", "cravings")][0] == "needs_review"                     # risk always
    assert review[("T-0003", "engagement", "attending_groups")][0] == "accepted"
    assert r.per_resident.set_index("resident_id").loc["T-0001", "note_referral_state"] == "closed"


def test_invented_quote_is_dropped_and_counted():
    stub = NotesStub({"Phone disconnected": [{"field": "referral", "value": "declined", "quote": "client said no"}]})
    r = run_notes(_raw(), stub)
    assert len(r.rejected) == 1
    assert not ((r.findings["resident_id"] == "T-0002") & (r.findings["value"] == "declined")).any()


def test_without_the_model_everything_is_unconfirmed():
    r = run_notes(_raw(), None)
    assert not r.model_ran and set(r.findings["review"]) == {"rules_only"}


def test_note_quotes_never_reach_agent_tables(hv):
    assert "note_findings" not in AGENT_TABLES
    assert "note_referral" in hv.residents.columns and "staff_note" not in hv.residents.columns


def test_notes_split_new_referrals_without_changing_the_recorded_count(hv):
    flags = {f.key: f for f in board(hv)}
    assert flags["waiting"].value == "7"
    assert flags["waiting"].detail == "1 waiting, 6 closed (staff notes)"
    assert "9 older referrals still have notes saying pending intake" in flags["waiting"].tip


def test_confirming_findings_removes_them_from_the_review_queue(hv, tmp_path):
    store = ReviewStore(tmp_path)
    q = review_queue(hv)
    recent = hv.residents[~hv.residents["matured"] & hv.residents["note_referral_state"].eq("closed")
                          & (hv.residents["stage"] == "referred")]
    for x in recent.itertuples():
        store.decide("harbourview", x.resident_id, "referral", x.note_referral, "confirm", "director")
    queued = {f"{x.resident_id}|referral|{x.note_referral}" for x in recent.itertuples()} & set(q["key"]) if len(q) else set()
    assert len(review_queue(hv, store.decisions("harbourview"))) == len(q) - len(queued)


def test_notes_about_people_who_left_follow_the_fiscal_year(hv):
    from axon.config import FiscalYear
    from axon.notes.summary import summarize
    all_years = {g.name: g for g in summarize(hv.residents, hv.note_findings)}
    fy25 = {g.name: g for g in summarize(hv.residents, hv.note_findings, FiscalYear(2025))}
    assert fy25["In the house now"].people == all_years["In the house now"].people  # where people are now
    assert not fy25["In the house now"].by_year and fy25["Referred, not admitted"].by_year
    assert fy25["Referred, not admitted"].people == 64 < all_years["Referred, not admitted"].people
