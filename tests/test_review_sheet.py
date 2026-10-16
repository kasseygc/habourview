"""Reading a completed review sheet back: corrections are parsed and validated, never guessed."""

from __future__ import annotations

import importlib.util
import sys

import pytest

from axon.config import ROOT

spec = importlib.util.spec_from_file_location("read_review_sheet", ROOT / "scripts" / "read_review_sheet.py")
rrs = importlib.util.module_from_spec(spec)
sys.modules["read_review_sheet"] = rrs  # dataclasses look their module up
spec.loader.exec_module(rrs)


def test_corrected_spec_is_read_from_free_text():
    text = 'Corrected reply: ... Corrected spec: {"metric": "occupancy", "chart": "table"} (remove group_by month).'
    assert rrs.corrected_spec(text) == {"metric": "occupancy", "chart": "table"}


def test_invalid_correction_is_left_for_a_person():
    row = rrs.Row("Questions", "o01", "q", "N", 'Corrected spec: {"metric": "occupancy", "group_by": ["outcome"]}')
    rrs.check_question(row, {"question": "q", "kind": "answer", "spec": {"metric": "occupancy"}})
    assert row.status == "left for a person" and "doesn't validate" in row.reason


@pytest.mark.parametrize("text, expected", [
    ("Expected categories: (nothing) under the existing taxonomy. Alternatively ...", []),
    ("Expected categories: passes: back from pass, engagement: doing well.", ["passes:pass_returned", "engagement:doing_well"]),
])
def test_corrected_note_categories(text, expected):
    assert rrs.corrected_findings(text) == expected


def test_unknown_category_is_rejected():
    with pytest.raises(ValueError):
        rrs.corrected_findings("Expected categories: passes: pass approved")


def test_written_spec_reads_back_the_same():
    s = {"metric": "residents_now", "group_by": ["current_status"],
         "filters": [{"field": "current_status", "op": "not_in", "values": ["not_admitted"]}], "chart": "bar"}
    import yaml
    assert rrs.compact(yaml.safe_load(rrs.flow(rrs.compact(s)))) == rrs.compact(s)
