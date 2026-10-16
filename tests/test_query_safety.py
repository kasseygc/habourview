"""Read-only enforcement, limits and tenant isolation. Each layer is tested on its own."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from axon.agent.compiler import compile_spec
from axon.agent.executor import QueryTimeout, run_query
from axon.agent.guard import UnsafeQuery, check_sql
from axon.agent.registry import FILTERS, METRICS
from axon.agent.narrate import narrate
from axon.agent.spec import LLMReply, QuerySpec
from axon.tenants import get_tenant
from axon.warehouse import load

ATTACKS = [
    "DROP TABLE residents",
    "INSERT INTO residents SELECT * FROM residents",
    "UPDATE residents SET current_status = 'alumni'",
    "DELETE FROM residents",
    "COPY residents TO 'leak.csv'",
    "ATTACH 'data/warehouse/testhouse.duckdb' AS ns",
    "SELECT * FROM ns.residents LIMIT 1",
    "SELECT * FROM read_csv('data/raw/testhouse_residents.csv') LIMIT 5",
    "SELECT * FROM 'data/raw/testhouse_residents.csv' LIMIT 1",
    "SELECT 1 FROM residents LIMIT 1; DELETE FROM residents",
    "SELECT getenv('HOME') FROM residents LIMIT 1",
    "SELECT * FROM dq_issues LIMIT 1",
    "SELECT * FROM meta LIMIT 1",
    "SELECT * FROM residents",
    "SELECT * FROM residents LIMIT 100000",
    "PRAGMA database_list",
    "SET enable_external_access = true",
    "INSTALL httpfs",
]


@pytest.mark.parametrize("sql", ATTACKS)
def test_guard_blocks(sql):
    with pytest.raises(UnsafeQuery):
        check_sql(sql)


@pytest.mark.parametrize("sql", [
    "INSERT INTO residents SELECT * FROM residents LIMIT 1",
    "CREATE TABLE x AS SELECT 1",
    "SELECT * FROM read_csv('data/raw/testhouse_residents.csv') LIMIT 1",
    "ATTACH 'data/warehouse/testhouse.duckdb' AS ns",
    "SET enable_external_access = true",
    "COPY residents TO 'out/leak.csv'",
])
def test_database_blocks_even_if_the_guard_is_bypassed(sql):
    with pytest.raises(Exception) as e:
        run_query(get_tenant("harbourview"), sql, [])
    assert "Permission" in type(e.value).__name__ or "Invalid" in type(e.value).__name__


def test_slow_queries_are_stopped():
    with pytest.raises(QueryTimeout):
        run_query(get_tenant("harbourview"), "SELECT count(*) FROM range(100000000000) a", [], timeout_s=0.5)


def test_row_cap_reports_truncation():
    r = run_query(get_tenant("harbourview"), "SELECT * FROM range(50)", [], max_rows=10)
    assert r.truncated and len(r.frame) == 10


def _every_valid_spec():
    for m in METRICS.values():
        dims = [[d] for d in m.dimensions] or [[]]
        for d in dims:
            group_by = list(dict.fromkeys([*m.required_dimensions[:1], *d]))[:2] if m.required_dimensions else d
            filters = [{"field": f, "op": "between", "values": [0, 400]} if FILTERS[f].kind == "number"
                       else {"field": f, "op": FILTERS[f].ops[-1], "values": [FILTERS[f].values[0]]} for f in m.filters]
            yield dict(metric=m.id, group_by=group_by, filters=filters,
                       time_window={"preset": "fy2025" if m.date_column else "all"}, chart=m.charts[0])


@pytest.mark.parametrize("spec", list(_every_valid_spec()), ids=lambda s: f"{s['metric']}-{'-'.join(s['group_by'])}")
def test_every_compiled_spec_passes_the_guard_runs_and_narrates(spec):
    parsed = QuerySpec.model_validate(spec)
    q = compile_spec(parsed)
    check_sql(q.sql)
    frame = run_query(get_tenant("harbourview"), q.sql, q.params).frame
    for variant in (parsed, parsed.model_copy(update={"group_by": [g for g in parsed.group_by if g in METRICS[parsed.metric].required_dimensions][:1]})):
        f = run_query(get_tenant("harbourview"), compile_spec(variant).sql, compile_spec(variant).params).frame
        assert isinstance(narrate(variant, f), str)
    assert isinstance(narrate(parsed, frame), str)


def test_spec_cannot_name_a_tenant():
    with pytest.raises(ValidationError):
        QuerySpec.model_validate({"metric": "admissions", "tenant": "testhouse"})
    with pytest.raises(ValidationError):
        LLMReply.model_validate({"action": "answer", "tenant_id": "testhouse",
                                 "spec": {"metric": "admissions"}})


def test_filter_values_are_bound_parameters_not_sql():
    q = compile_spec(QuerySpec.model_validate(
        {"metric": "discharges", "filters": [{"field": "discharge_reason", "values": ["self_discharge"]}]}))
    assert "self_discharge" not in q.sql and "self_discharge" in q.params


@pytest.mark.parametrize("bad", [
    {"metric": "occupancy", "group_by": ["fee_status"]},                       # not allowed for metric
    {"metric": "stay_outcomes"},                                              # needs how it ended or where they went
    {"metric": "followup_outcomes", "group_by": ["outcome"]},                  # needs horizon
    {"metric": "residents_now", "time_window": {"preset": "fy2025"}},         # point in time
    {"metric": "admissions", "time_window": {"preset": "custom"}},             # custom needs dates
    {"metric": "admissions", "filters": [{"field": "fee_status", "values": ["free"]}]},
    {"metric": "admissions", "chart": "pie"},
    {"metric": "resident_names"},
])
def test_invalid_specs_are_rejected(bad):
    with pytest.raises(ValidationError):
        QuerySpec.model_validate(bad)


def test_same_spec_gives_each_house_only_its_own_data():
    q = compile_spec(QuerySpec.model_validate({"metric": "residents_now", "group_by": ["current_status"]}))
    for tenant_id in ("harbourview", "testhouse"):
        got = int(run_query(get_tenant(tenant_id), q.sql, q.params).frame["n"].sum())
        expected = int((load(get_tenant(tenant_id)).residents["current_status"] != "not_admitted").sum())
        assert got == expected
    hv = run_query(get_tenant("harbourview"), q.sql, q.params).frame
    ns = run_query(get_tenant("testhouse"), q.sql, q.params).frame
    assert int(hv["n"].sum()) != int(ns["n"].sum())
