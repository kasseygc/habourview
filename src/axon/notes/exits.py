"""How each stay ended (completion vs discharge) and where people went next.

Exit type uses the recorded discharge reason first. Only when the reason is "other" or blank do
the staff notes fill it in, and such rows are marked `exit_from_notes` so they can be shown, and
held back from funder figures, until staff confirm. Destination comes only from the notes.
"""

from __future__ import annotations

import pandas as pd

RECORDED = {
    "completed": "completed",
    "self_discharge": "left_by_choice",
    "administrative": "discharged_by_house",
    "transfer": "transferred",
}
FROM_NOTE_DISCHARGE = {
    "self_discharge": "left_by_choice",
    "peer_conflict": "left_by_choice",
    "rule_violations": "discharged_by_house",
    "use_on_premises": "discharged_by_house",
    "violence": "discharged_by_house",
    "positive_drug_test": "discharged_by_house",
    "incarceration": "custody",
    "transfer_detox": "transferred",
    "transfer_hospital": "transferred",
    "moved_region": "transferred",
}
# When a note gives several reasons, the more specific one wins.
PRIORITY = ["custody", "transferred", "discharged_by_house", "left_by_choice"]
DESTINATION_PRIORITY = ["custody", "hospital", "detox", "another_program", "sober_living", "home_or_family"]


def derive(residents: pd.DataFrame, findings: pd.DataFrame) -> pd.DataFrame:
    """Return resident_id, exit_type, exit_from_notes, destination for admitted residents."""
    note_discharge = findings[findings["field"] == "discharge"].groupby("resident_id")["value"].apply(set).to_dict()
    note_destination = findings[findings["field"] == "destination"].groupby("resident_id")["value"].apply(set).to_dict()
    rows = []
    for r in residents.itertuples():
        if not r.admitted:
            continue
        from_notes = False
        if r.in_residence:
            exit_type = "still_in_program"
        elif r.completion_group == "completed":
            exit_type = "completed"
        elif r.discharge_reason in RECORDED:
            exit_type = RECORDED[r.discharge_reason]
        else:  # "other", or no reason recorded
            mapped = {FROM_NOTE_DISCHARGE[v] for v in note_discharge.get(r.resident_id, set()) if v in FROM_NOTE_DISCHARGE}
            exit_type = next((t for t in PRIORITY if t in mapped), "other_or_unknown")
            from_notes = exit_type != "other_or_unknown"
        dest = note_destination.get(r.resident_id, set())
        rows.append({
            "resident_id": r.resident_id,
            "exit_type": exit_type,
            "exit_from_notes": from_notes,
            "destination": None if r.in_residence else next((d for d in DESTINATION_PRIORITY if d in dest), None),
        })
    return pd.DataFrame(rows, columns=["resident_id", "exit_type", "exit_from_notes", "destination"])
