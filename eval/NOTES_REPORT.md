# Staff-note extraction: evaluation

70 labelled notes (47 from the Harbourview file, 18 written in other words). Model `claude-opus-5-5`, mode `replay`.

Model answers are not recorded yet; only the rules are scored.

| System | Notes | Precision | Recall | F1 |
|---|---|---|---|---|
| rules | file | 100% | 100% | 100% |
| rules | varied | 89% | 28% | 42% |
| rules | all | 98% | 73% | 84% |

Recall by field, all notes:

| System | referral | discharge | risk | engagement | passes | destination |
|---|---|---|---|---|---|---|
| rules | 72% | 81% | 50% | 73% | 75% | 78% |

Quotes not found in the note (rejected by the validator): 0

## Misses: rules

- “Chose a day program near work instead.”: missed referral:declined; extra nothing
- “Intake booked for next Tuesday.”: missed referral:pending_intake; extra nothing
- “No bed yet - next in line when one frees up.”: missed referral:waitlisted; extra nothing
- “Needs medical clearance first, sent to withdrawal mgmt.”: missed referral:referred_out; extra nothing
- “Didn't turn up for assessment, court notified.”: missed referral:no_show; extra nothing
- “Tearful in group, says she feels hopeless lately. Booked w/ counsellor.”: missed risk:low_mood; extra nothing
- “Reports strong urges to use after family visit.”: missed risk:cravings; extra nothing
- “Went to 2 NA and 1 AA mtg this wk, now has a sponsor.”: missed engagement:attending_groups; extra nothing
- “Started part-time work at a grocery store.”: missed engagement:work; extra nothing
- “Altercation in the kitchen, staff stepped in, no injuries.”: missed risk:incident; extra nothing
- “Walked out Sunday morning without telling staff.”: missed discharge:self_discharge; extra nothing
- “Sent to ER, admitted to the medical ward.”: missed destination:hospital, discharge:transfer_hospital; extra nothing
- “Picked up by police on an old warrant.”: missed destination:custody, discharge:incarceration; extra nothing
- “Hasn't come to aftercare in a month, not returning calls.”: missed engagement:aftercare_missed, engagement:no_recent_contact; extra nothing
- “Spoke at the alumni dinner, doing great.”: missed engagement:doing_well; extra nothing
- “Res. back from weekend pass, appears well, attending NA 3x/wk”: missed engagement:doing_well; extra nothing
- “Didn't come back from overnight pass; staff left a message.”: missed passes:pass_late_or_missed; extra passes:pass_returned
- “Graduated, now living with family and working.”: missed engagement:work; extra nothing
