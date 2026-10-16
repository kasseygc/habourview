# Harbourview House analytics

A take-home for Axon Health. Dashboard, notes extraction, and plain-English question answering for a fictional 24-bed recovery home. Resident data stays secure and redacted at every step. All data is synthetic.

**Read first:** [docs/Harbourview_writeup.docx](docs/Harbourview_writeup.docx) — one page of decisions, assumptions, trade-offs and next steps, plus Task C as an appendix.

![The dashboard: four tabs showing flow, occupancy, outcomes, and staff notes](docs/screenshots/flow.png)

| Documentation |  |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Design, safety layers, PHI handling, evaluation |
| [eval/REPORT.md](eval/REPORT.md), [NOTES_REPORT.md](eval/NOTES_REPORT.md), [REDACTION_REPORT.md](eval/REDACTION_REPORT.md) | Evaluation results |
| [docs/review/evaluation_review_completed.xlsx](docs/review/evaluation_review_completed.xlsx) | Label review record |

## Dashboard

![Occupancy: 90% of beds filled, a typical stay of 95 days](docs/screenshots/occupancy.png)
![Outcomes: completion, engaged at 6 months 46–85%, follow-up results](docs/screenshots/outcomes.png)
![Notes: structured fields read from staff notes](docs/screenshots/notes.png)

## Questions in plain English

![Ask: monthly occupancy, a clarification, and a declined person-specific question](docs/screenshots/ask.png)

## Evaluation

| Check | Result |
|---|---|
| Questions: unsafe answers (must be 0) | 0 of 48 |
| Questions: right kind of reply | 98% |
| Questions: exact answer | 71% |
| Questions: headline numbers stated | 85% |
| Staff notes: findings found, precision | 94%, 91% |
| Name redaction: caught, false alarms | 33 of 34, none |
| Automated tests | 194 passing |

## Run it

Needs [uv](https://docs.astral.sh/uv/). It installs Python 3.12 and every dependency, including the
local name detector used for redaction (spaCy's large English model, about 400 MB, downloaded once).

```bash
uv sync
uv run axon build                          # one read-only DuckDB file per house
uv run streamlit run app/streamlit_app.py  # the app, at http://localhost:8501
```

The language model is free and local. Without it, the app and evaluations replay recorded answers,
so everything works offline for the recorded questions. With it, new questions take about 10
seconds on a laptop. The app never saves what people type; only the evaluation commands record.

```bash
brew install ollama
ollama serve                 # in its own terminal
ollama pull gemma3:12b       # Google Gemma 3, 12B, about 8 GB
```

Other commands:

```bash
uv run pytest                              # all tests
uv run axon eval                           # score the 48 questions (add --mode record to re-run the model)
uv run axon notes-eval                     # score note extraction on 70 labelled notes
uv run axon redaction-eval                 # score name redaction, layer by layer
uv run axon audit-verify                   # check the audit log hasn't been edited
uv run axon report --fy 2025               # write the funder report to out/
uv run python scripts/read_review_sheet.py # read a completed review sheet back (--apply to update gold files)
uv run python scripts/generate_data.py     # regenerate the test house (seeded)
```

## What's where

```
data/raw/            harbourview_residents.csv (given), testhouse_residents.csv (generated),
                     harbourview_directory.csv (synthetic client and contact names, used only to redact)
src/axon/
  ingest.py          read and type-check a house's CSV
  model.py           build the shared tables: residents, followups, nightly_census
  quality.py         data-quality rules, each with its treatment
  metrics/           funnel, occupancy, length of stay, outcomes
  status.py          the four status-strip facts
  notes/             staff notes to fields: schema, rules, model, merge, evaluation
  redact.py          redaction: identifiers, names by rule, the house name list, a local name detector
  suppress.py        small-count hiding for the funder export
  agent/             catalogue, spec, compiler, SQL guard, executor, glossary, house definitions,
                     prompt, model client, answer templates, audit log
  report/funder.py   the funder export
app/                 the Streamlit app
eval/                labelled questions, notes and redaction sentences; recordings; reports; review record
scripts/             generate_data.py (test house), read_review_sheet.py (human review read-back)
tests/               metric edge cases, privacy, query safety, tenant isolation, agent flow
docs/                write-up, architecture, review sheets, screenshots
```

## Notes

`data/raw/testhouse_residents.csv` is generated for tenant isolation tests only (seed 7).

I used Claude (Claude Code) as a pair programmer. I made every design decision; Claude wrote code and first drafts to those decisions. All data used during development was synthetic.
