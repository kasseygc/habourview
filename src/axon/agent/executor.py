"""Run a checked query against one house's file, read-only, with limits (D-14, D-15).

Even if the compiler and the guard were both bypassed, this connection cannot write,
cannot read any other file, cannot load extensions and cannot change those settings.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import duckdb
import pandas as pd

from axon.config import QUERY_ROW_LIMIT, QUERY_TIMEOUT_SECONDS
from axon.tenants import Tenant


class QueryTimeout(RuntimeError):
    pass


@dataclass
class QueryResult:
    frame: pd.DataFrame
    truncated: bool
    elapsed_ms: int


def connect_read_only(tenant: Tenant) -> duckdb.DuckDBPyConnection:
    if not tenant.warehouse_path.exists():
        raise FileNotFoundError(f"No warehouse for {tenant.id}; run `uv run axon build`")
    return duckdb.connect(
        str(tenant.warehouse_path),
        read_only=True,
        config={
            "enable_external_access": False,
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
            "allow_community_extensions": False,
            "threads": 2,
            "memory_limit": "256MB",
            "lock_configuration": True,
        },
    )


def run_query(
    tenant: Tenant,
    sql: str,
    params: list,
    *,
    timeout_s: float = QUERY_TIMEOUT_SECONDS,
    max_rows: int = QUERY_ROW_LIMIT,
) -> QueryResult:
    con = connect_read_only(tenant)
    timer = threading.Timer(timeout_s, con.interrupt)
    started = time.perf_counter()
    timer.start()
    try:
        cur = con.execute(sql, params)
        rows = cur.fetchmany(max_rows + 1)
        columns = [d[0] for d in cur.description]
    except duckdb.InterruptException as e:
        raise QueryTimeout(f"query stopped after {timeout_s:.0f}s") from e
    finally:
        timer.cancel()
        con.close()
    truncated = len(rows) > max_rows
    frame = pd.DataFrame(rows[:max_rows], columns=columns)
    return QueryResult(frame=frame, truncated=truncated, elapsed_ms=int((time.perf_counter() - started) * 1000))
