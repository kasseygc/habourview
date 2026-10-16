"""Metric logic: hand-built edge cases first, then the figures quoted in the write-up."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from axon.config import FiscalYear
from axon.metrics.funnel import funnel
from axon.metrics.occupancy import monthly_occupancy
from axon.metrics.outcomes import outcomes
from axon.metrics.stays import stays
from axon.model import build_model
from axon.stats import kaplan_meier, km_median, summarize
from tests.conftest import AS_OF, make_raw

# ---------------------------------------------------------------- edge cases on tiny data


def test_bed_is_filled_from_admission_up_to_not_including_discharge():
    raw = make_raw([
        dict(referral_date="2025-12-01", intake_date="2025-12-01", admission_date="2026-01-01",
             discharge_date="2026-01-03", current_status="discharged", discharge_reason="self_discharge"),
    ])
    census = build_model(raw, AS_OF).nightly_census.set_index("night")["residents"]
    assert census[pd.Timestamp("2026-01-01")] == 1
    assert census[pd.Timestamp("2026-01-02")] == 1
    assert census[pd.Timestamp("2026-01-03")] == 0


def test_person_still_in_house_fills_every_night_to_the_extract_date():
    raw = make_raw([dict(referral_date="2025-12-01", admission_date="2026-01-10", current_status="phase_1")])
    census = build_model(raw, AS_OF).nightly_census
    assert census["night"].max() == pd.Timestamp("2026-01-14")  # last observed night
    assert census["residents"].sum() == 5  # 10th to 14th


def test_missing_discharge_date_is_estimated_for_occupancy_only():
    raw = make_raw([
        dict(referral_date="2025-01-01", admission_date="2025-01-01", discharge_date="2025-01-11",
             current_status="discharged", discharge_reason="self_discharge"),
        dict(referral_date="2025-02-01", admission_date="2025-02-01", current_status="discharged",
             discharge_reason="administrative"),
    ])
    m = build_model(raw, AS_OF)
    r = m.residents.set_index("resident_id")
    assert m.estimated_stay_days == 10
    assert r.loc["T-0002", "occupancy_end_date"] == pd.Timestamp("2025-02-11")
    assert pd.isna(r.loc["T-0002", "los_days"])  # length of stay stays unknown
    assert m.nightly_census["residents_estimated"].sum() == 10


def test_admitted_without_intake_counts_as_reaching_intake_but_has_no_intake_timing():
    raw = make_raw([dict(referral_date="2025-01-01", admission_date="2025-01-20", current_status="phase_3")])
    r = build_model(raw, AS_OF).residents.iloc[0]
    assert r["reached_intake"] and r["admitted"]
    assert pd.isna(r["days_referral_to_intake"]) and pd.isna(r["days_intake_to_admission"])
    assert r["days_referral_to_admission"] == 19


def test_negative_stage_gap_is_excluded_from_timing():
    raw = make_raw([dict(referral_date="2025-01-10", intake_date="2025-01-05")])
    assert pd.isna(build_model(raw, AS_OF).residents.iloc[0]["days_referral_to_intake"])


def test_maturity_cutoff_is_inclusive():
    raw = make_raw([dict(referral_date="2025-11-16"), dict(referral_date="2025-11-17")])
    matured = build_model(raw, AS_OF).residents.set_index("resident_id")["matured"]
    assert matured["T-0001"] and not matured["T-0002"]


@pytest.mark.parametrize("discharge, due", [("2025-07-15", True), ("2025-07-16", False)])
def test_followup_is_due_on_the_six_month_anniversary(discharge, due):
    raw = make_raw([dict(referral_date="2025-01-01", admission_date="2025-02-01", discharge_date=discharge,
                         current_status="alumni", discharge_reason="completed",
                         followup_6m=None if due else "not_yet_due", followup_12m="not_yet_due")])
    f = build_model(raw, AS_OF).followups
    row = f[f["horizon_months"] == 6].iloc[0]
    assert bool(row["is_due"]) is due
    assert row["outcome"] == ("not_recorded" if due else "not_yet_due")


def test_graduate_status_decides_completion_when_reason_is_blank():
    raw = make_raw([
        dict(referral_date="2025-01-01", admission_date="2025-01-02", discharge_date="2025-05-01", current_status="aftercare"),
        dict(referral_date="2025-01-01", admission_date="2025-01-02", discharge_date="2025-02-01", current_status="discharged"),
    ])
    r = build_model(raw, AS_OF).residents.set_index("resident_id")
    assert list(r["discharge_reason"]) == ["not_recorded", "not_recorded"]
    assert r.loc["T-0001", "completion_group"] == "completed"
    assert r.loc["T-0002", "completion_group"] == "early_leaver"


def test_kaplan_meier_counts_ongoing_stays_as_censored():
    # 4 people: left at 10, 20; still in at 15 and 30.
    curve = kaplan_meier(pd.Series([10, 15, 20, 30]), pd.Series([True, False, True, False]))
    s = dict(zip(curve["days"], curve["share_still_in_house"]))
    assert s[10] == pytest.approx(0.75)
    assert s[20] == pytest.approx(0.75 * 0.5)  # 2 at risk at day 20, 1 leaves
    assert km_median(curve) == 20


def test_quantiles_match_linear_interpolation():
    s = summarize(pd.Series([1, 2, 3, 4, 100]))
    assert (s.n, s.median, s.p90) == (5, 3.0, pytest.approx(61.6))


# ---------------------------------------------------------------- Harbourview figures


def test_harbourview_fy2025_funnel(hv):
    f = funnel(hv.residents, FiscalYear(2025), AS_OF)
    assert (f.cohort_n, f.matured_n) == (141, 129)
    assert [s.n for s in f.stages] == [129, 103, 72]
    assert f.cutoff == date(2025, 11, 16)
    assert int(f.recent["n"].sum()) == 12


def test_harbourview_fy2024_is_fully_mature(hv):
    f = funnel(hv.residents, FiscalYear(2024), AS_OF)
    assert f.cohort_n == f.matured_n == 59
    assert [s.n for s in f.stages] == [59, 42, 33]


def test_harbourview_occupancy_never_exceeds_capacity(hv):
    assert hv.nightly_census["residents"].max() <= hv.capacity
    o = monthly_occupancy(hv.nightly_census, FiscalYear(2025))
    assert o.rate == pytest.approx(0.899, abs=0.001)
    assert len(o.monthly) == 12 and not o.monthly["partial_month"].any()


def test_harbourview_stays_fy2025(hv):
    s = stays(hv.residents, FiscalYear(2025))
    assert s.admitted_n == 81
    assert s.ongoing.n == 14
    assert s.missing_discharge_date == 2
    assert s.km_median_days == 95  # higher than finished-only median: censoring matters
    assert s.finished_all.median == 86


def test_outcomes_use_everyone_due_as_denominator(hv):
    r = outcomes(hv.followups, 6)
    assert r.due_n == 51
    assert r.counts == {"engaged_in_recovery": 21, "relapse_reported": 8, "lost_to_follow_up": 15,
                        "unknown": 3, "not_recorded": 4}
    assert r.engaged_worst_case == pytest.approx(21 / 51)
    assert r.engaged_best_case == pytest.approx(43 / 51)
    # The survivorship-biased figure (21/29 = 72%) must not be what we report.
    assert r.engaged_worst_case < 0.5


def test_twelve_month_outcomes(hv):
    r = outcomes(hv.followups, 12)
    assert r.due_n == 11 and r.engaged == 1


def test_outcomes_by_fiscal_year_place_people_by_discharge_date(hv):
    from axon.config import FiscalYear
    fy24, fy25 = outcomes(hv.followups, 6, FiscalYear(2024)), outcomes(hv.followups, 6, FiscalYear(2025))
    assert (fy24.due_n, fy25.due_n) == (8, 41)
    # Two follow-ups were recorded for people with no discharge date: only in the all-years total.
    assert outcomes(hv.followups, 6).due_n == fy24.due_n + fy25.due_n + 2
    assert round(fy25.engaged_worst_case, 2) == 0.46 and round(fy25.engaged_best_case, 2) == 0.85
