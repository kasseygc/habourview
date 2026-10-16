"""Second line of defence: check the SQL itself before it runs.

The compiler already produces safe SQL. This guard assumes it might not, and rejects
anything that is not a single SELECT over the agent's tables using allow-listed functions,
with a LIMIT no higher than the configured maximum.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from axon.config import QUERY_ROW_LIMIT
from axon.warehouse import AGENT_TABLES


class UnsafeQuery(ValueError):
    pass


# sqlglot models AND/OR, CASE and CAST as function nodes too. Everything else is rejected,
# including table functions such as read_csv and system functions such as getenv.
ALLOWED_FUNCTIONS = {
    "and", "or", "not", "count", "sum", "avg", "min", "max", "case", "if", "cast", "coalesce", "nullif",
    "round", "abs", "timetostr", "year", "quarter", "month",
    "median", "groupconcat", "logicalor",  # median(), string_agg(), bool_or()
}
# Node types that write, change state or reach outside the database.
FORBIDDEN = tuple(
    getattr(exp, name)
    for name in (
        "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "AlterTable", "Command", "Copy",
        "Pragma", "Set", "Use", "Transaction", "Commit", "Rollback", "Attach", "Detach", "Install",
        "LoadData", "Into", "Grant", "Revoke", "TruncateTable", "Export",
    )
    if hasattr(exp, name)
)


def check_sql(sql: str, max_rows: int = QUERY_ROW_LIMIT) -> None:
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise UnsafeQuery(f"could not parse SQL: {e}") from e
    if len(statements) != 1:
        raise UnsafeQuery("exactly one statement is allowed")
    root = statements[0]
    if not isinstance(root, exp.Select):
        raise UnsafeQuery(f"only SELECT is allowed, got {root.key.upper()}")

    for node in root.walk():
        if isinstance(node, FORBIDDEN):
            raise UnsafeQuery(f"{node.key.upper()} is not allowed")
        if isinstance(node, exp.Table):
            if node.args.get("db") or node.args.get("catalog"):
                raise UnsafeQuery("qualified table names are not allowed")
            if not isinstance(node.this, exp.Identifier) or node.name not in AGENT_TABLES:
                raise UnsafeQuery(f"table {node.sql()!r} is not allowed")
        if isinstance(node, exp.Func):
            name = (node.name if isinstance(node, exp.Anonymous) else node.key).lower()
            if name not in ALLOWED_FUNCTIONS:
                raise UnsafeQuery(f"function {name!r} is not allowed")

    limit = root.args.get("limit")
    if limit is None:
        raise UnsafeQuery("a LIMIT is required")
    try:
        n = int(limit.expression.name)
    except (AttributeError, ValueError):
        raise UnsafeQuery("LIMIT must be a number") from None
    if n > max_rows:
        raise UnsafeQuery(f"LIMIT {n} is above the maximum of {max_rows}")
