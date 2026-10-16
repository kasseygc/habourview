# Human review of the evaluation sets

Read from `docs/review/evaluation_review_completed.xlsx` on 15 Oct 2026 by `scripts/read_review_sheet.py`; corrections written to the gold files.

- Questions (45): 37 confirmed, 3 corrected, 5 not reviewed
- Notes (70): 69 confirmed, 1 corrected

| Sheet | ID | Item | Result | Change or reason |
|---|---|---|---|---|
| Questions | o05 | How many people were in the house on October 11 2025? | applied | `{metric: occupancy, group_by: [month], time_window: {preset: custom, start: 2025-10-11, end: 2025-10-11}, chart: table}  →  {metric: occupancy, time_window: {preset: custom, start: 2025-10-11, end: 2025-10-11}, chart: table}` |
| Questions | f05 | How many people were lost to follow-up at 6 months? | applied | `{metric: followup_outcomes, group_by: [outcome], filters: [{field: horizon, values: [6m]}], chart: stacked_bar}  →  {metric: followup_outcomes, filters: [{field: outcome, values: [lost_to_follow_up]}, {field: horizon, values: [6m]}], chart: bar}` |
| Questions | r03 | Break down everyone we have admitted by their current status. | applied | `{metric: residents_now, group_by: [current_status], chart: bar}  →  {metric: residents_now, group_by: [current_status], filters: [{field: current_status, op: not_in, values: [not_admitted]}], chart: bar}` |
| Notes | g067 | Weekend pass approved for a family visit. | applied | `[passes:pass_taken]  →  []` the correction also suggests an alternative; the first option was applied |

Not reviewed: x04, x05, x06, x07, x08.
