# Name redaction: evaluation

43 labelled sentences (eval/redaction_gold.yaml): names with and without a relationship word, names in typed questions, and look-alikes that must survive (NA, AA, weekdays, places, organisations).

| Layers | Names caught | Words wrongly removed | Name-free sentences tagged | ms per sentence |
|---|---|---|---|---|
| Rules only | 18/34 (53%) | 0 | 0 | 0.0 |
| Rules + house directory | 30/34 (88%) | 0 | 0 | 0.0 |
| Rules + detector (en_core_web_sm) | 27/34 (79%) | 0 | 0 | 1.7 |
| Rules + directory + detector (en_core_web_sm) | 33/34 (97%) | 0 | 0 | 1.6 |
| Rules + detector (en_core_web_lg) | 32/34 (94%) | 0 | 0 | 2.2 |
| Rules + directory + detector (en_core_web_lg) | 33/34 (97%) | 0 | 0 | 2.3 |

## Rules only

- missed: Kevin (Called Kevin, no answer.)
- missed: Linda (Spoke w/ Linda re: visit on Sunday.)
- missed: Kevin (Kevin came by with groceries.)
- missed: Marcus (Left VM for Marcus, will try again Tues.)
- missed: Jordan (Jordan from Ontario Works confirmed funding.)
- missed: Brandon (Res says Brandon is a bad influence, wants no contact.)
- missed: Sarah (Emergency contact changed to Sarah Thompson.)
- missed: Thompson (Emergency contact changed to Sarah Thompson.)
- missed: Tyler (Res and Tyler had a verbal argument in the kitchen.)
- missed: Daniel (Res requested that Daniel be removed from visitor list.)
- missed: Kayla (Kayla and res attended AA together.)
- missed: Priya (Priya dropped off clothes; res in good spirits.)
- missed: Kevin (How is Kevin doing?)
- missed: Linda (Did Linda call back?)
- missed: Marcus (Has Marcus been to group this week?)
- missed: Tyler (What did staff note about Tyler?)

## Rules + house directory

- missed: Jordan (Jordan from Ontario Works confirmed funding.)
- missed: Brandon (Res says Brandon is a bad influence, wants no contact.)
- missed: Sarah (Emergency contact changed to Sarah Thompson.)
- missed: Thompson (Emergency contact changed to Sarah Thompson.)

## Rules + detector (en_core_web_sm)

- missed: Marcus (Left VM for Marcus, will try again Tues.)
- missed: Jordan (Jordan from Ontario Works confirmed funding.)
- missed: Tyler (Res and Tyler had a verbal argument in the kitchen.)
- missed: Kayla (Kayla and res attended AA together.)
- missed: Priya (Priya dropped off clothes; res in good spirits.)
- missed: Marcus (Has Marcus been to group this week?)
- missed: Tyler (What did staff note about Tyler?)

## Rules + directory + detector (en_core_web_sm)

- missed: Jordan (Jordan from Ontario Works confirmed funding.)

## Rules + detector (en_core_web_lg)

- missed: Marcus (Left VM for Marcus, will try again Tues.)
- missed: Jordan (Jordan from Ontario Works confirmed funding.)

## Rules + directory + detector (en_core_web_lg)

- missed: Jordan (Jordan from Ontario Works confirmed funding.)
