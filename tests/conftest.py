from __future__ import annotations

import json
import os

# Tests never call the API: model answers come only from recordings in eval/cassettes.
os.environ["AXON_LLM_MODE"] = "replay"
from datetime import date

import pandas as pd
import pytest

from axon.agent.audit import AuditLog
from axon.agent.definitions import DefinitionStore
from axon.agent.llm import LLMCall
from axon.agent.pipeline import Agent
from axon.ingest import EXPECTED_COLUMNS, read_residents
from axon.tenants import get_tenant
from axon.warehouse import build_all, load


@pytest.fixture(scope="session", autouse=True)
def built():
    build_all()


@pytest.fixture(scope="session")
def hv():
    return load(get_tenant("harbourview"))


@pytest.fixture(scope="session")
def hv_raw():
    return read_residents(get_tenant("harbourview").csv_path)


def make_raw(rows: list[dict], capacity: int = 2) -> pd.DataFrame:
    """A tiny typed frame in the same shape read_residents returns."""
    full = []
    for i, r in enumerate(rows, start=1):
        base = dict.fromkeys(EXPECTED_COLUMNS)
        base.update(resident_id=f"T-{i:04d}", current_status="not_admitted", bed_capacity=capacity, staff_note=None)
        base.update(r)
        full.append(base)
    df = pd.DataFrame(full, columns=EXPECTED_COLUMNS)
    for c in ["referral_date", "intake_date", "admission_date", "discharge_date"]:
        df[c] = pd.to_datetime(df[c])
    df["entrance_fee"] = pd.to_numeric(df["entrance_fee"])
    df["fee_waived"] = df["fee_waived"].astype("boolean")
    df["bed_capacity"] = df["bed_capacity"].astype("Int64")
    return df


AS_OF = date(2026, 1, 15)


class StubLLM:
    """Stands in for Claude. Maps a substring of the question to a reply."""

    def __init__(self, replies: dict[str, dict | str]):
        self.replies = replies
        self.calls: list[str] = []

    def complete(self, system, user_text, schema):
        self.calls.append(user_text)
        for needle, reply in self.replies.items():
            if needle.lower() in user_text.lower():
                text = reply if isinstance(reply, str) else json.dumps(reply)
                return LLMCall(text, "stub", "stub", "end_turn")
        raise AssertionError(f"StubLLM has no reply for: {user_text!r}")


def answer(spec: dict) -> dict:
    tw = spec.setdefault("time_window", {"preset": "all", "start": None, "end": None})
    tw.setdefault("start", None)
    tw.setdefault("end", None)
    spec.setdefault("filters", [])
    spec.setdefault("group_by", [])
    return {"action": "answer", "spec": spec, "unclear_terms": [], "candidate_metrics": [], "decline_reason": None}


@pytest.fixture
def make_agent(tmp_path):
    def _make(replies: dict) -> tuple[Agent, StubLLM]:
        stub = StubLLM(replies)
        agent = Agent(llm=stub, store=DefinitionStore(tmp_path / "defs"), audit=AuditLog(tmp_path / "audit.jsonl"))
        return agent, stub

    return _make
