"""Turn a validated spec into one parameterised, read-only SELECT (D-11).

Identifiers come only from the registry. Every user-influenced value is a bound parameter.
"""

from __future__ import annotations

from dataclasses import dataclass

from axon.agent.registry import DIMENSIONS, FILTERS, METRICS
from axon.agent.spec import QuerySpec
from axon.config import QUERY_ROW_LIMIT


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: list
    columns: list[str]  # grouping columns, in order


def compile_spec(spec: QuerySpec, row_limit: int = QUERY_ROW_LIMIT) -> CompiledQuery:
    m = METRICS[spec.metric]
    where = [f"({m.base_where})"]
    params: list = []

    for f in spec.filters:
        field = FILTERS[f.field]
        if f.field == "fee_status":
            where.append(field.sql.format(params="?"))
            params.append(f.values[0] == "waived")
        elif f.field == "horizon":
            where.append(field.sql.format(params="?"))
            params.append(int(f.values[0].rstrip("m")))
        else:
            where.append(field.sql.format(params=", ".join("?" for _ in f.values)))
            params.extend(f.values)

    bounds = spec.time_window.bounds()
    if bounds and m.date_column:
        where.append(f"{m.date_column} >= ? AND {m.date_column} < ? + INTERVAL 1 DAY")
        params.extend([bounds[0], bounds[1]])

    group_exprs = []
    for g in spec.group_by:
        d = DIMENSIONS[g]
        expr = d.sql.format(date=m.date_column) if d.needs_date else d.sql
        group_exprs.append(f"{expr} AS {g}")

    select = ", ".join([*group_exprs, m.select])
    sql = f"SELECT {select} FROM {m.table} WHERE {' AND '.join(where)}"
    if spec.group_by:
        positions = ", ".join(str(i + 1) for i in range(len(spec.group_by)))
        sql += f" GROUP BY {positions} ORDER BY {positions}"
    sql += f" LIMIT {int(row_limit)}"
    return CompiledQuery(sql=sql, params=params, columns=list(spec.group_by))
