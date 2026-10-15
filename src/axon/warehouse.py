"""One DuckDB file per house (D-14). Built here; opened read-only everywhere else."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone

import duckdb
import pandas as pd

from axon.config import AS_OF, WAREHOUSE_DIR, maturity_cutoff
from axon.ingest import read_residents
from axon.model import build_model
from axon.quality import check
from axon.tenants import TENANTS, Tenant

# The only tables the agent may query. dq_issues and meta are for the dashboard.
AGENT_TABLES = ("residents", "followups", "nightly_census")


@dataclass
class Warehouse:
    residents: pd.DataFrame
    followups: pd.DataFrame
    nightly_census: pd.DataFrame
    dq_issues: pd.DataFrame
    meta: dict

    @property
    def capacity(self) -> int:
        return int(self.meta["capacity"])

    @property
    def as_of(self) -> date:
        return pd.Timestamp(self.meta["as_of"]).date()


def build_tenant(tenant: Tenant, as_of: date = AS_OF) -> dict:
    raw = read_residents(tenant.csv_path)
    model = build_model(raw, as_of)
    issues = check(raw, model, as_of)
    meta = {
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "as_of": pd.Timestamp(as_of),
        "maturity_cutoff": pd.Timestamp(maturity_cutoff(as_of)),
        "capacity": model.capacity,
        "estimated_stay_days": model.estimated_stay_days,
        "source_sha256": hashlib.sha256(tenant.csv_path.read_bytes()).hexdigest(),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = tenant.warehouse_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        for name, frame in [
            ("residents", model.residents),
            ("followups", model.followups),
            ("nightly_census", model.nightly_census),
            ("dq_issues", issues),
            ("meta", pd.DataFrame([meta])),
        ]:
            con.register("frame", _duckdb_friendly(frame))
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM frame")
            con.unregister("frame")
    finally:
        con.close()
    os.replace(tmp, tenant.warehouse_path)
    return meta


def build_all(as_of: date = AS_OF) -> list[dict]:
    return [build_tenant(t, as_of) for t in TENANTS.values() if t.csv_path.exists()]


def load(tenant: Tenant) -> Warehouse:
    if not tenant.warehouse_path.exists():
        build_tenant(tenant)
    con = duckdb.connect(str(tenant.warehouse_path), read_only=True)
    try:
        frames = {name: con.execute(f"SELECT * FROM {name}").df() for name in (*AGENT_TABLES, "dq_issues", "meta")}
    finally:
        con.close()
    return Warehouse(
        residents=frames["residents"],
        followups=frames["followups"],
        nightly_census=frames["nightly_census"],
        dq_issues=frames["dq_issues"],
        meta=frames["meta"].iloc[0].to_dict(),
    )


def _duckdb_friendly(frame: pd.DataFrame) -> pd.DataFrame:
    """Plain numpy/object dtypes so DuckDB infers clean column types."""
    out = frame.copy()
    out.attrs = {}
    for col in out.columns:
        dtype = out[col].dtype
        if isinstance(dtype, pd.BooleanDtype):
            out[col] = out[col].astype("object").where(out[col].notna(), None)
        elif isinstance(dtype, (pd.Int64Dtype, pd.Float64Dtype)):
            out[col] = out[col].astype("float64") if isinstance(dtype, pd.Float64Dtype) else out[col].astype("object").where(out[col].notna(), None)
        elif pd.api.types.is_string_dtype(dtype) and not pd.api.types.is_datetime64_any_dtype(dtype):
            out[col] = out[col].astype("object").where(out[col].notna(), None)
    return out
