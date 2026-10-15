"""Reporting rules in one place. Every constant here is a decision recorded in DECISIONS.md."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
AUDIT_DIR = DATA_DIR / "audit"
DEFINITIONS_DIR = DATA_DIR / "definitions"
OUT_DIR = ROOT / "out"

# D-01: the extract date. Latest date in the file; follow-up statuses agree with it exactly.
AS_OF = date(2026, 1, 15)

# D-02: a referral needs this many days before the extract to count in conversion rates.
# Observed referral -> admission P90 is 41 days, max 71.
MATURITY_DAYS = 60

# D-08: funder export hides counts from 1 to 4.
SMALL_CELL_THRESHOLD = 5

FOLLOWUP_HORIZONS_MONTHS = (6, 12)

# Agent execution limits (D-15).
QUERY_ROW_LIMIT = 500
QUERY_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class FiscalYear:
    """Axon customers report January to December."""

    year: int

    @property
    def start(self) -> date:
        return date(self.year, 1, 1)

    @property
    def end(self) -> date:
        return date(self.year, 12, 31)

    @property
    def label(self) -> str:
        return f"FY{self.year}"


def maturity_cutoff(as_of: date = AS_OF) -> date:
    """Referrals on or before this date have had MATURITY_DAYS to progress."""
    return as_of - timedelta(days=MATURITY_DAYS)
