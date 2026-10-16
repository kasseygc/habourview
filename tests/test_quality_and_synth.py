from __future__ import annotations

import json

import pandas as pd

from axon.config import RAW_DIR
from axon.ingest import read_residents
from axon.model import build_model
from axon.quality import check
from axon.synth import generate, to_csv_frame
from axon.tenants import get_tenant


def test_harbourview_issues_are_found_with_resident_ids(hv):
    by_rule = hv.dq_issues.groupby("rule")["resident_id"].apply(set).to_dict()
    assert by_rule["Admitted without an intake date"] == {"HV-0009", "HV-0072", "HV-0095", "HV-0114", "HV-0150", "HV-0155"}
    assert by_rule["Intake before referral"] == {"HV-0041", "HV-0149"}
    assert by_rule["Left the house but no discharge date"] == {"HV-0031", "HV-0072", "HV-0136"}
    assert by_rule["No discharge reason"] == {"HV-0067", "HV-0104"}
    assert by_rule["6-month follow-up due but blank"] == {"HV-0018", "HV-0071", "HV-0076", "HV-0083"}
    assert (hv.dq_issues["treatment"].str.len() > 0).all()


def test_generator_is_deterministic_and_matches_committed_file():
    a, b = generate(seed=7), generate(seed=7)
    pd.testing.assert_frame_equal(a.frame, b.frame)
    committed = pd.read_csv(RAW_DIR / "testhouse_residents.csv", dtype=str, keep_default_na=False)
    pd.testing.assert_frame_equal(to_csv_frame(a.frame).astype(str).reset_index(drop=True), committed)
    assert json.loads((RAW_DIR / "testhouse_manifest.json").read_text()) == a.manifest


def test_checks_find_every_planted_problem():
    raw = read_residents(get_tenant("testhouse").csv_path)
    found = check(raw, build_model(raw)).groupby("rule")["resident_id"].apply(set).to_dict()
    manifest = json.loads((RAW_DIR / "testhouse_manifest.json").read_text())
    for rule, ids in manifest.items():
        if rule == "PHI-like note":
            continue
        assert set(ids) <= found.get(rule, set()), rule


def test_generated_house_respects_capacity_before_estimates():
    raw = read_residents(get_tenant("testhouse").csv_path)
    census = build_model(raw).nightly_census
    actual = census["residents"] - census["residents_estimated"]
    assert actual.max() <= 16
