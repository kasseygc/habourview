from __future__ import annotations

from axon.status import board


def test_harbourview_status_strip_is_neutral(hv):
    flags = {f.key: f for f in board(hv)}
    assert list(flags) == ["beds", "waiting", "calls", "missing"]
    assert flags["beds"].value == "15 / 24" and flags["beds"].detail == "9 beds open"
    assert flags["waiting"].value == "7"
    assert flags["calls"].value == "14"
    assert flags["missing"].value == "4"
    assert all(f.status == "neutral" and f.badge is None for f in flags.values())
