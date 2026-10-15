"""The approved catalogue: the only metrics, groupings, filters and charts a spec can name.

The LLM chooses from this list; it never writes SQL. Every SQL fragment the compiler uses
comes from here, keyed by an allow-listed id, so no user or model text reaches SQL except
as a bound parameter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from axon.ingest import DISCHARGE_REASONS, STATUSES


@dataclass(frozen=True)
class Dimension:
    id: str
    label: str
    sql: str  # may contain {date}, replaced by the metric's date column
    needs_date: bool = False


@dataclass(frozen=True)
class FilterField:
    id: str
    label: str
    values: tuple[str, ...]
    sql: str  # a predicate with one placeholder per value: {params}


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    description: str
    table: str
    select: str  # aggregate expressions
    base_where: str = "TRUE"
    date_column: str | None = None
    dimensions: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()
    required_filters: tuple[str, ...] = ()
    required_dimensions: tuple[str, ...] = ()
    charts: tuple[str, ...] = ("bar", "table")
    value_column: str = "n"
    order_by: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


DIMENSIONS: dict[str, Dimension] = {
    d.id: d
    for d in [
        Dimension("month", "Month", "strftime({date}, '%Y-%m')", needs_date=True),
        Dimension("quarter", "Quarter", "CAST(year({date}) AS VARCHAR) || '-Q' || CAST(quarter({date}) AS VARCHAR)", needs_date=True),
        Dimension("fiscal_year", "Fiscal year (Jan-Dec)", "'FY' || CAST(year({date}) AS VARCHAR)", needs_date=True),
        Dimension("fee_status", "Entrance fee", "CASE WHEN fee_waived THEN 'waived' WHEN NOT fee_waived THEN 'paid' ELSE 'unknown' END"),
        Dimension("discharge_reason", "Discharge reason", "discharge_reason"),
        Dimension("completion_group", "Completed or left early", "completion_group"),
        Dimension("current_status", "Current status", "current_status"),
        Dimension("outcome", "Follow-up outcome", "outcome"),
    ]
}

FILTERS: dict[str, FilterField] = {
    f.id: f
    for f in [
        FilterField("fee_status", "Entrance fee", ("waived", "paid"), "fee_waived = {params}"),
        FilterField("discharge_reason", "Discharge reason", (*DISCHARGE_REASONS, "not_recorded"), "discharge_reason IN ({params})"),
        FilterField("completion_group", "Completed or left early", ("completed", "early_leaver"), "completion_group IN ({params})"),
        FilterField("current_status", "Current status", tuple(STATUSES), "current_status IN ({params})"),
        FilterField("horizon", "Follow-up point", ("6m", "12m"), "horizon_months = {params}"),
    ]
}

TIME_DIMS = ("month", "quarter", "fiscal_year")

METRICS: dict[str, Metric] = {
    m.id: m
    for m in [
        Metric(
            "referrals", "Referrals received", "Count of referrals, dated by referral date.",
            table="residents", select="COUNT(*) AS n", date_column="referral_date",
            dimensions=TIME_DIMS, charts=("bar", "line", "table"),
        ),
        Metric(
            "intakes", "Intake assessments", "Count of intake assessments, dated by intake date. "
            "People admitted without a recorded intake date cannot be placed in a month.",
            table="residents", select="COUNT(*) AS n", base_where="intake_date IS NOT NULL",
            date_column="intake_date", dimensions=(*TIME_DIMS, "fee_status"), filters=("fee_status",),
            charts=("bar", "line", "table"),
        ),
        Metric(
            "admissions", "Admissions", "Count of admissions, dated by admission date.",
            table="residents", select="COUNT(*) AS n", base_where="admitted",
            date_column="admission_date", dimensions=(*TIME_DIMS, "fee_status"), filters=("fee_status",),
            charts=("bar", "line", "stacked_bar", "table"),
        ),
        Metric(
            "discharges", "Discharges (leaving the house)",
            "Count of people leaving the house, dated by discharge date, for any reason including completion. "
            "Stays with no recorded discharge date are not counted.",
            table="residents", select="COUNT(*) AS n", base_where="left_house AND discharge_date IS NOT NULL",
            date_column="discharge_date",
            dimensions=(*TIME_DIMS, "discharge_reason", "completion_group", "fee_status"),
            filters=("discharge_reason", "completion_group", "fee_status"),
            charts=("bar", "stacked_bar", "line", "table"),
        ),
        Metric(
            "occupancy", "Bed occupancy",
            "Share of beds filled, counted each night: bed-nights used / (beds x nights). "
            "Also returns average and peak residents per night.",
            table="nightly_census",
            select=(
                "SUM(residents) * 1.0 / SUM(capacity) AS occupancy_rate, AVG(residents) AS avg_residents, "
                "MAX(residents) AS peak_residents, MAX(capacity) AS beds, COUNT(*) AS nights"
            ),
            date_column="night", dimensions=TIME_DIMS, required_dimensions=("month", "quarter", "fiscal_year"),
            charts=("line", "bar", "table"), value_column="occupancy_rate",
        ),
        Metric(
            "followup_outcomes", "Follow-up outcomes",
            "Everyone who has left the house and whose 6- or 12-month follow-up date has passed, split by outcome "
            "(engaged in recovery, relapse reported, lost to follow-up, unknown, due but not recorded). "
            "Includes people who left early. Dated by discharge date.",
            table="followups",
            select="COUNT(*) AS n",
            base_where="is_due", date_column="discharge_date",
            dimensions=("outcome", "completion_group", "fee_status"),
            filters=("horizon", "completion_group", "fee_status", "discharge_reason"),
            required_filters=("horizon",), required_dimensions=("outcome",),
            charts=("stacked_bar", "bar", "table"),
        ),
        Metric(
            "followup_engaged_rate", "Engaged in recovery at follow-up, with best and worst case",
            "Of everyone whose follow-up was due: how many were confirmed engaged in recovery, plus the best case "
            "(everyone unreached is engaged) and worst case (nobody unreached is engaged). Dated by discharge date.",
            table="followups",
            select=(
                "COUNT(*) AS due, "
                "SUM(CASE WHEN outcome = 'engaged_in_recovery' THEN 1 ELSE 0 END) AS engaged, "
                "SUM(CASE WHEN outcome = 'relapse_reported' THEN 1 ELSE 0 END) AS relapse, "
                "SUM(CASE WHEN outcome IN ('lost_to_follow_up', 'unknown', 'not_recorded') THEN 1 ELSE 0 END) AS no_outcome"
            ),
            base_where="is_due", date_column="discharge_date",
            dimensions=("completion_group", "fee_status"),
            filters=("horizon", "completion_group", "fee_status", "discharge_reason"),
            required_filters=("horizon",), charts=("bar", "table"), value_column="engaged",
        ),
        Metric(
            "residents_now", "Residents by current status (as of the extract date)",
            "Point-in-time count of people by their current status. Not dated; a time window does not apply.",
            table="residents", select="COUNT(*) AS n", base_where="current_status <> 'not_admitted'",
            dimensions=("current_status",), filters=("current_status",), charts=("bar", "table"),
        ),
    ]
}

CHARTS = ("bar", "line", "stacked_bar", "table")
TIME_PRESETS = ("all", "fy2024", "fy2025", "custom")
DECLINE_REASONS = ("row_level", "out_of_scope", "write_request", "other_house", "unsafe")
