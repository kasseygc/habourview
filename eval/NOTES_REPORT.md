# Staff-note extraction: evaluation

70 labelled notes (47 from the Harbourview file, 23 written in other words). Model `gemma3:12b`, mode `replay`.

| System | Notes | Precision | Recall | F1 |
|---|---|---|---|---|
| rules | file | 100% | 100% | 100% |
| rules | varied | 88% | 25% | 39% |
| rules | all | 98% | 73% | 84% |
| model | file | 91% | 78% | 84% |
| model | varied | 92% | 79% | 85% |
| model | all | 91% | 78% | 84% |
| rules + model | file | 93% | 100% | 96% |
| rules + model | varied | 88% | 82% | 85% |
| rules + model | all | 91% | 94% | 92% |

Recall by field, all notes:

| System | referral | discharge | risk | engagement | passes | destination |
|---|---|---|---|---|---|---|
| rules | 72% | 81% | 50% | 73% | 67% | 78% |
| model | 100% | 81% | 100% | 69% | 100% | 33% |
| rules + model | 100% | 94% | 100% | 92% | 100% | 78% |

Quotes not found in the note (rejected by the validator): 5
Notes where rules and model disagree (sent to review): 32

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

## Misses: model

- “Graduated. Volunteers at house occasionally.”: missed nothing; extra destination:home_or_family
- “Left AMA after conflict w/ peer.”: missed discharge:self_discharge; extra nothing
- “Self-discharged. Stated wanted to go home.”: missed destination:home_or_family; extra nothing
- “Graduated program. Attending weekly aftercare group.”: missed nothing; extra destination:home_or_family
- “aftercare check-in by phone - doing well, employed”: missed engagement:aftercare_attending; extra nothing
- “Moved to program in home region.”: missed discharge:moved_region; extra nothing
- “transferred to higher level of care (detox)”: missed destination:detox; extra nothing
- “Discharged - see paper file”: missed nothing; extra discharge:self_discharge
- “Incarcerated - outstanding warrant”: missed destination:custody; extra nothing
- “started part-time job search, good engagement in groups”: missed engagement:attending_groups; extra nothing
- “Res. settling in, attending all groups. Some cravings reported.”: missed engagement:attending_groups; extra nothing
- “Transferred to hospital for medical care.”: missed destination:hospital; extra nothing
- “Sister [NAME] dropped off clothes; res in good spirits.”: missed engagement:doing_well; extra nothing
- “Mom ([NAME]) called asking about visiting hrs, call back [PHONE].”: missed nothing; extra referral:unreachable
- “doing well. sponsor identified”: missed engagement:doing_well; extra nothing
- “Tearful in group, says she feels hopeless lately. Booked w/ counsellor.”: missed nothing; extra engagement:aftercare_planned
- “Sent to ER, admitted to the medical ward.”: missed destination:hospital; extra nothing
- “Picked up by police on an old warrant.”: missed destination:custody, discharge:incarceration; extra nothing
- “Hasn't come to aftercare in a month, not returning calls.”: missed engagement:aftercare_missed; extra nothing
- “Spoke at the alumni dinner, doing great.”: missed engagement:alumni_involved; extra nothing
- “Res. back from weekend pass, appears well, attending NA 3x/wk”: missed engagement:doing_well; extra nothing
- “Weekend pass approved for a family visit.”: missed nothing; extra passes:pass_taken

## Misses: rules + model

- “Graduated. Volunteers at house occasionally.”: missed nothing; extra destination:home_or_family
- “Graduated program. Attending weekly aftercare group.”: missed nothing; extra destination:home_or_family
- “Discharged - see paper file”: missed nothing; extra discharge:self_discharge
- “Mom ([NAME]) called asking about visiting hrs, call back [PHONE].”: missed nothing; extra referral:unreachable
- “Tearful in group, says she feels hopeless lately. Booked w/ counsellor.”: missed nothing; extra engagement:aftercare_planned
- “Sent to ER, admitted to the medical ward.”: missed destination:hospital; extra nothing
- “Picked up by police on an old warrant.”: missed destination:custody, discharge:incarceration; extra nothing
- “Hasn't come to aftercare in a month, not returning calls.”: missed engagement:aftercare_missed; extra nothing
- “Res. back from weekend pass, appears well, attending NA 3x/wk”: missed engagement:doing_well; extra nothing
- “Weekend pass approved for a family visit.”: missed nothing; extra passes:pass_taken
- “Didn't come back from overnight pass; staff left a message.”: missed nothing; extra passes:pass_returned
