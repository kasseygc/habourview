from __future__ import annotations

from axon.status import board
from axon.tenants import get_tenant
from axon.warehouse import load


def test_harbourview_status_board(hv):
    flags = {f.key: f for f in board(hv)}
    assert flags["beds"].value == "15 / 24" and flags["beds"].status == "amber"
    assert flags["waiting"].value == "7"
    assert flags["calls"].value == "14" and flags["calls"].status == "green"
    assert flags["missing"].value == "4" and flags["missing"].status == "amber"
    assert all(f.status in {"red", "amber", "green"} for f in flags.values())
    assert all(f.action for f in flags.values() if f.status != "green")


def test_estimate_driven_over_capacity_is_not_red():
    flags = {f.key: f for f in board(load(get_tenant("northshore")))}
    assert "estimated" in flags["data"].detail
    assert flags["data"].status == "amber"
